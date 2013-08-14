"""
Tests for :mod:`otter.scheduler`
"""

from twisted.trial.unittest import TestCase
from twisted.internet import defer
from twisted.internet.task import Clock

import mock

from silverberg.lock import BusyLockError
from silverberg.cassandra.ttypes import TimedOutException

from otter.scheduler import SchedulerService
from otter.test.utils import iMock, patch, CheckFailure
from otter.models.interface import (
    IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection)
from otter.rest.application import set_store
from otter.models.cass import LOCK_TABLE_NAME
from otter.models.interface import NoSuchPolicyError, NoSuchScalingGroupError
from otter.controller import CannotExecutePolicyError


class SchedulerTestCase(TestCase):
    """
    Tests for :mod:`SchedulerService`
    """

    def setUp(self):
        """
        mock all the dependencies of SchedulingService that includes cass store,
        store's fetch and delete events methods, scaling group on which controller
        will execute scaling policy. Hence, controller.maybe_execute_scaling_policy.
        twisted.internet.task.Clock is used to simulate time
        """

        self.mock_store = iMock(IScalingGroupCollection, IScalingScheduleCollection)
        self.mock_group = iMock(IScalingGroup)
        self.mock_store.get_scaling_group.return_value = self.mock_group

        self.returns = [None]

        def _responses(*args):
            result = self.returns.pop(0)
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.mock_store.fetch_batch_of_events.side_effect = _responses

        self.mock_store.update_delete_events.return_value = defer.succeed(None)

        self.mock_generate_transaction_id = patch(
            self, 'otter.scheduler.generate_transaction_id',
            return_value='transaction-id')
        set_store(self.mock_store)
        self.addCleanup(set_store, None)

        # mock out modify state
        self.mock_state = mock.MagicMock(spec=[])  # so nothing can call it

        def _mock_modify_state(modifier, *args, **kwargs):
            modifier(self.mock_group, self.mock_state, *args, **kwargs)
            return defer.succeed(None)

        self.mock_group.modify_state.side_effect = _mock_modify_state

        self.maybe_exec_policy = patch(self, 'otter.scheduler.maybe_execute_scaling_policy')

        def _mock_with_lock(lock, func, *args, **kwargs):
            return defer.maybeDeferred(func, *args, **kwargs)

        self.mock_lock = patch(self, 'otter.scheduler.BasicLock')
        self.mock_with_lock = patch(self, 'otter.scheduler.with_lock')
        self.mock_with_lock.side_effect = _mock_with_lock
        self.slv_client = mock.MagicMock()
        self.otter_log = patch(self, 'otter.scheduler.otter_log')

        self.clock = Clock()
        self.scheduler_service = SchedulerService(100, 1, self.slv_client, self.clock)

        self.otter_log.bind.assert_called_once_with(system='otter.scheduler')
        self.log = self.otter_log.bind.return_value

        self.next_cron_occurrence = patch(self, 'otter.scheduler.next_cron_occurrence')
        self.next_cron_occurrence.return_value = 'newtrigger'

    def validate_calls(self, d, fetch_returns, update_delete_args):
        """
        Validate all the calls made in the service w.r.t to the events
        """
        fetch_call_count = len(fetch_returns)
        events = [event for fetch_return in fetch_returns for event in fetch_return]
        num_events = len(events)
        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, fetch_call_count)
        if update_delete_args:
            self.assertEqual(self.mock_store.update_delete_events.call_args_list,
                             [mock.call(delete_events, update_events)
                              for delete_events, update_events in update_delete_args])
        self.assertEqual(self.mock_group.modify_state.call_count, num_events)
        self.assertEqual(self.mock_store.get_scaling_group.call_args_list,
                         [mock.call(mock.ANY, e['tenantId'], e['groupId']) for e in events])
        self.assertEqual(self.maybe_exec_policy.mock_calls,
                         [mock.call(mock.ANY, 'transaction-id', self.mock_group,
                          self.mock_state, policy_id=event['policyId']) for event in events])

    def test_empty(self):
        """
        No policies are executed when ``fetch_batch_of_events`` return empty list
        i.e. no events are there before now
        """
        self.returns = [[]]
        d = self.scheduler_service.check_for_events(100)
        self.validate_calls(d, [[]], None)
        self.assertFalse(self.mock_store.update_delete_events.called)
        self.log.bind.assert_called_once_with(scheduler_run_id=mock.ANY, utcnow=mock.ANY)
        self.log.bind.return_value.msg.assert_called_once_with('Checking for events')

    def test_one(self):
        """
        policy is executed when its corresponding event is there before now
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': None}]
        self.returns = [events]

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, [events], [(['pol44'], [])])

    def test_policy_exec_logs(self):
        """
        The scheduler logs `CannotExecutePolicyError` as msg instead of err
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': 'c1'}]
        self.returns = [events]
        self.mock_group.modify_state.side_effect = (
            lambda *_: defer.fail(CannotExecutePolicyError('t', 'g', 'p', 'w')))

        d = self.scheduler_service.check_for_events(100)

        self.assertIsNone(self.successResultOf(d))
        self.log.bind.return_value.bind(tenant_id='1234', scaling_group_id='scal44',
                                        policy_id='pol44')
        self.log.bind.return_value.bind.return_value.msg.assert_has_calls(
            [mock.call('Executing policy'),
             mock.call('Cannot execute policy',
                       reason=CheckFailure(CannotExecutePolicyError))])
        self.assertFalse(self.log.bind.return_value.bind.return_value.err.called)

    def test_many(self):
        """
        Events are fetched and processed as batches of 100. Its corresponding policies
        are executed.
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                    'trigger': 'now', 'cron': None} for i in range(100)]
        events2 = [{'tenantId': '1234', 'groupId': 'scal45', 'policyId': 'pol45',
                    'trigger': 'now', 'cron': None} for i in range(100)]
        self.returns = [events1, events2, []]
        fetch_returns = self.returns[:]

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, fetch_returns, [(['pol44'] * 100, []), (['pol45'] * 100, [])])

    def test_timer_works(self):
        """
        The scheduler executes every x seconds
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                    'trigger': 'now', 'cron': None} for i in range(30)]
        events2 = [{'tenantId': '1234', 'groupId': 'scal45', 'policyId': 'pol45',
                    'trigger': 'now', 'cron': None} for i in range(20)]
        self.returns = [events1, events2]

        # events not fetched before startService
        self.validate_calls(defer.succeed(None), [], None)

        # events fetched after calling startService
        self.scheduler_service.startService()
        self.validate_calls(defer.succeed(None), [events1], [(['pol44'] * 30, [])])

        # events are fetched again after timer expires
        self.clock.advance(1)
        self.validate_calls(defer.succeed(None), [events1, events2],
                            [(['pol44'] * 30, []), (['pol45'] * 20, [])])

    def test_timer_works_on_error(self):
        """
        The scheduler executes every x seconds even if an occurs occurs while fetching events
        """
        # Copy fetch function from setUp and set it to fail
        fetch_func = self.mock_store.fetch_batch_of_events.side_effect
        self.mock_store.fetch_batch_of_events.side_effect = None
        self.mock_store.fetch_batch_of_events.return_value = defer.fail(TimedOutException())

        # Start service and see if update_delete_events got called
        self.scheduler_service.startService()
        self.assertFalse(self.mock_store.update_delete_events.called)

        # fix fetch function and advance clock to see if works next time
        self.mock_store.fetch_batch_of_events.side_effect = fetch_func
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': None} for i in range(30)]
        self.returns = [events]
        self.clock.advance(1)
        self.validate_calls(defer.succeed(None),
                            [[], events],  # first [] to account for failed fetch call
                            [(['pol44'] * 30, [])])

    def test_called_with_lock(self):
        """
        ``fetch_and_process`` is called with a lock
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                    'trigger': 'now', 'cron': None} for i in range(100)]
        events2 = [{'tenantId': '1234', 'groupId': 'scal45', 'policyId': 'pol45',
                    'trigger': 'now', 'cron': None} for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, [events1, events2],
                            [(['pol44'] * 100, []), (['pol45'] * 20, [])])

        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.call_count, 2)
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)] * 2)

    def test_does_nothing_on_no_lock(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock. It
        does not call ``fetch_and_process``
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                    'trigger': 'now', 'cron': None} for i in range(100)]
        events2 = [{'tenantId': '1234', 'groupId': 'scal45', 'policyId': 'pol45',
                    'trigger': 'now', 'cron': None} for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)
        with_lock_impl = lambda *args: defer.fail(BusyLockError(LOCK_TABLE_NAME, 'schedule'))
        self.mock_with_lock.side_effect = with_lock_impl

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, [], None)
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)])
        self.log.msg.assert_called_once_with("Couldn't get lock to process events",
                                             reason=CheckFailure(BusyLockError))

    def test_does_nothing_on_no_lock_second_time(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock after
        finishing first batch of 100 events. It does not call ``fetch_and_process`` second time
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                    'trigger': 'now', 'cron': None} for i in range(100)]
        events2 = [{'tenantId': '1234', 'groupId': 'scal45', 'policyId': 'pol45',
                    'trigger': 'now', 'cron': None} for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        _with_lock_first_time = [True]

        def _with_lock(lock, func, *args, **kwargs):
            if _with_lock_first_time[0]:
                _with_lock_first_time[0] = False
                return defer.maybeDeferred(func, *args, **kwargs)
            return defer.fail(BusyLockError(LOCK_TABLE_NAME, 'schedule'))

        self.mock_with_lock.side_effect = _with_lock

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, [events1], [(['pol44'] * 100, [])])
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)] * 2)
        self.log.msg.assert_called_once_with("Couldn't get lock to process events",
                                             reason=CheckFailure(BusyLockError))

    def test_cron_updates(self):
        """
        The scheduler updates cron events
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': 'c1'} for i in range(30)]
        self.returns = [events]

        d = self.scheduler_service.check_for_events(100)

        exp_updated_events = []
        for event in events:
            event['trigger'] = 'newtrigger'
            exp_updated_events.append(event)
        self.validate_calls(d, [events], [([], exp_updated_events)])

    def test_cron_updates_and_deletes(self):
        """
        The scheduler updates cron events and deletes at-style events
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': 'c1'},
                  {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol45',
                   'trigger': 'now', 'cron': None},
                  {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol46',
                   'trigger': 'now', 'cron': 'c2'}]
        self.returns = [events]

        d = self.scheduler_service.check_for_events(100)

        exp_deleted_events = ['pol45']
        exp_updated_events = []
        for i in [0, 2]:
            event = events[i]
            event['trigger'] = 'newtrigger'
            exp_updated_events.append(event)
        self.validate_calls(d, [events], [(exp_deleted_events, exp_updated_events)])

    def test_nopolicy_or_group_events_deleted(self):
        """
        The scheduler does not update deleted policy/group's (that give NoSuchPolicyError or
        NoSuchScalingGroupError) events (for cron-style events) and deletes them
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                   'trigger': 'now', 'cron': 'c1'},
                  {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol45',
                   'trigger': 'now', 'cron': 'c2'},
                  {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol46',
                   'trigger': 'now', 'cron': 'c3'},
                  {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol47',
                   'trigger': 'now', 'cron': None}]
        self.returns = [events]

        events_indexes = range(len(events))

        def _mock_modify_state(modifier, *args, **kwargs):
            index = events_indexes.pop(0)
            if index == 0:
                return defer.fail(NoSuchPolicyError('1234', 'scal44', 'pol44'))
            if index == 1:
                return defer.fail(NoSuchScalingGroupError('1234', 'scal44'))
            modifier(self.mock_group, self.mock_state, *args, **kwargs)
            return defer.succeed(None)

        self.mock_group.modify_state.side_effect = _mock_modify_state

        d = self.scheduler_service.check_for_events(100)

        exp_delete_events = ['pol44', 'pol45', 'pol47']
        events[2]['trigger'] = 'newtrigger'
        exp_update_events = [events[2]]

        # Not using validate_call since maybe_execute_scaling_policy calls do not match
        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 1)
        self.mock_store.update_delete_events.assert_called_once_with(exp_delete_events,
                                                                     exp_update_events)
        self.assertEqual(self.mock_group.modify_state.call_count, len(events))
        self.assertEqual(self.mock_store.get_scaling_group.call_args_list,
                         [mock.call(mock.ANY, e['tenantId'], e['groupId']) for e in events])
