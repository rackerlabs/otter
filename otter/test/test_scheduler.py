"""
Tests for :mod:`otter.scheduler`
"""

from twisted.trial.unittest import TestCase
from twisted.internet import defer
from twisted.internet.task import Clock

import mock
from datetime import datetime, timedelta

from otter.scheduler import (
    SchedulerService, check_events_in_bucket, process_events, add_cron_events, execute_event)
from otter.test.utils import iMock, patch, CheckFailure, mock_log, DeferredFunctionMixin
from otter.models.interface import (
    IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection)
from otter.models.interface import NoSuchPolicyError, NoSuchScalingGroupError
from otter.controller import CannotExecutePolicyError


class SchedulerTests(TestCase):
    """
    Tests for `scheduler.py`
    """

    def setUp(self):
        """
        mock common dependencies of methods in scheduler.py
        """
        self.mock_store = iMock(IScalingGroupCollection, IScalingScheduleCollection)
        self.mock_generate_transaction_id = patch(
            self, 'otter.scheduler.generate_transaction_id',
            return_value='transaction-id')


class SchedulerServiceTests(SchedulerTests, DeferredFunctionMixin):
    """
    Tests for `SchedulerService`
    """

    def setUp(self):
        """
        mock all the dependencies of SchedulingService that includes logging,
        store's fetch_and_delete, TxKazooClient stuff, TimerService, check_events_in_bucket
        and twisted.internet.task.Clock is used to simulate time
        """
        super(SchedulerServiceTests, self).setUp()

        otter_log = patch(self, 'otter.scheduler.otter_log')
        self.log = mock_log()
        otter_log.bind.return_value = self.log

        self.kz_client = mock.Mock(spec=['SetPartitioner'])
        self.kz_partition = mock.MagicMock(allocating=False, release=False, failed=False,
                                           acquired=False)
        self.kz_client.SetPartitioner.return_value = self.kz_partition
        self.zk_partition_path = '/part_path'
        self.time_boundary = 15
        self.buckets = range(1, 10)

        self.clock = Clock()
        self.scheduler_service = SchedulerService(
            100, 1, self.mock_store, self.kz_client, self.zk_partition_path,
            self.time_boundary, self.buckets, self.clock, threshold=600)
        otter_log.bind.assert_called_once_with(system='otter.scheduler')
        self.timer_service = patch(self, 'otter.scheduler.TimerService')

        self.check_events_in_bucket = patch(self, 'otter.scheduler.check_events_in_bucket')

        self.returns = []
        self.setup_func(self.mock_store.get_oldest_event)

    def test_start_service(self):
        """
        startService() calls super's startService() and creates SetPartitioner object
        """
        self.scheduler_service.startService()
        self.kz_client.SetPartitioner.assert_called_once_with(
            self.zk_partition_path, set=set(self.buckets), time_boundary=self.time_boundary)
        self.assertEqual(self.scheduler_service.kz_partition, self.kz_partition)
        self.timer_service.startService.assert_called_once_with(self.scheduler_service)

    def test_stop_service(self):
        """
        stopService() calls super's stopService() and stops the allocation if it
        is already acquired
        """
        self.scheduler_service.startService()
        self.kz_partition.acquired = True
        d = self.scheduler_service.stopService()
        self.timer_service.stopService.assert_called_once_with(self.scheduler_service)
        self.kz_partition.finish.assert_called_once_with()
        self.assertEqual(self.kz_partition.finish.return_value, d)

    def test_health_check_after_threshold(self):
        """
        `service.health_check` returns False when trigger time is above threshold
        """
        self.kz_partition.acquired = True
        self.scheduler_service.startService()
        self.kz_partition.__iter__.return_value = [2, 3]
        now = datetime.utcnow()
        returns = [{'trigger': now - timedelta(hours=1), 'version': 'v1'},
                   {'trigger': now - timedelta(seconds=2), 'version': 'v1'}]
        self.returns = returns[:]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d), (False, {'old_events': [returns[0]],
                                                           'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls([mock.call(2), mock.call(3)])

    def test_health_check_before_threshold(self):
        """
        `service.health_check` returns True when trigger time is below threshold
        """
        self.kz_partition.acquired = True
        self.scheduler_service.startService()
        self.kz_partition.__iter__.return_value = [2, 3]
        now = datetime.utcnow()
        self.returns = [{'trigger': now + timedelta(hours=1), 'version': 'v1'},
                        {'trigger': now + timedelta(seconds=2), 'version': 'v1'}]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d), (True, {'old_events': [],
                                                          'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls([mock.call(2), mock.call(3)])

    def test_health_check_None(self):
        """
        `service.health_check` returns True when there are no triggers
        """
        self.kz_partition.acquired = True
        self.scheduler_service.startService()
        self.kz_partition.__iter__.return_value = [2, 3]
        self.returns = [None, None]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d), (True, {'old_events': [],
                                                          'buckets': [2, 3]}))
        self.mock_store.get_oldest_event.assert_has_calls([mock.call(2), mock.call(3)])

    def test_health_check_not_acquired(self):
        """
        `service.health_check` returns False when partition is not acquired
        """
        self.kz_partition.acquired = False
        self.scheduler_service.startService()
        self.kz_partition.__iter__.return_value = [2, 3]

        d = self.scheduler_service.health_check()

        self.assertEqual(self.successResultOf(d), (False, {'reason': 'Not acquired'}))
        self.assertFalse(self.mock_store.get_oldest_event.called)

    def test_stop_service_allocating(self):
        """
        stopService() does not stop the allocation (i.e. call finish) if it is not acquired
        """
        self.scheduler_service.startService()
        d = self.scheduler_service.stopService()
        self.assertFalse(self.kz_partition.finish.called)
        self.assertIsNone(d)

    def test_reset(self):
        """
        reset() starts new partition based on new path
        """
        self.scheduler_service.reset('/new_path')
        self.assertEqual(self.scheduler_service.zk_partition_path, '/new_path')
        self.kz_client.SetPartitioner.assert_called_once_with(
            '/new_path', set=set(self.buckets), time_boundary=self.time_boundary)
        self.assertEqual(self.scheduler_service.kz_partition,
                         self.kz_client.SetPartitioner.return_value)

    def test_reset_same_path(self):
        """
        reset() raises error on same path
        """
        self.assertRaises(ValueError, self.scheduler_service.reset, '/part_path')
        self.assertFalse(self.kz_client.SetPartitioner.called)

    def test_check_events_allocating(self):
        """
        `check_events` logs message and does not check events in buckets when
        buckets are still allocating
        """
        self.kz_partition.allocating = True
        self.scheduler_service.startService()
        self.scheduler_service.check_events(100)
        self.log.msg.assert_called_with('Partition allocating')

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_release(self):
        """
        `check_events` logs message and does not check events in buckets when
        partitioning has changed. It calls release_set() to re-partition
        """
        self.kz_partition.release = True
        self.scheduler_service.startService()
        self.scheduler_service.check_events(100)
        self.log.msg.assert_called_with('Partition changed. Repartitioning')
        self.kz_partition.release_set.assert_called_once_with()

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_failed(self):
        """
        `check_events` logs message and does not check events in buckets when
        partitioning has failed. It creates a new partition
        """
        self.kz_partition.failed = True
        self.scheduler_service.startService()

        # after starting change SetPartitioner return value to check if
        # new value is set in self.scheduler_service.kz_partition
        new_kz_partition = mock.MagicMock()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.scheduler_service.check_events(100)
        self.log.msg.assert_called_with('Partition failed. Starting new')

        # Called once when starting and now again when partition failed
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.zk_partition_path, set=set(self.buckets),
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.scheduler_service.kz_partition, new_kz_partition)

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(new_kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    def test_check_events_bad_state(self):
        """
        `self.kz_partition.state` is none of the exepected values. `check_events`
        logs it as err and starts a new partition
        """
        self.kz_partition.state = 'bad'
        self.scheduler_service.startService()

        # after starting change SetPartitioner return value to check if
        # new value is set in self.scheduler_service.kz_partition
        new_kz_partition = mock.MagicMock()
        self.kz_client.SetPartitioner.return_value = new_kz_partition

        self.scheduler_service.check_events(100)

        self.log.err.assert_called_with('Unknown state bad. This cannot happen. Starting new')
        self.kz_partition.finish.assert_called_once_with()

        # Called once when starting and now again when got bad state
        self.assertEqual(self.kz_client.SetPartitioner.call_args_list,
                         [mock.call(self.zk_partition_path, set=set(self.buckets),
                                    time_boundary=self.time_boundary)] * 2)
        self.assertEqual(self.scheduler_service.kz_partition, new_kz_partition)

        # Ensure others are not called
        self.assertFalse(self.kz_partition.__iter__.called)
        self.assertFalse(new_kz_partition.__iter__.called)
        self.assertFalse(self.check_events_in_bucket.called)

    @mock.patch('otter.scheduler.datetime')
    def test_check_events_acquired(self, mock_datetime):
        """
        `check_events` checks events in each bucket when they are partitoned.
        """
        self.kz_partition.acquired = True
        self.scheduler_service.startService()
        self.kz_partition.__iter__.return_value = [2, 3]
        self.scheduler_service.log = mock.Mock()
        mock_datetime.utcnow.return_value = 'utcnow'

        responses = [4, 5]
        self.check_events_in_bucket.side_effect = lambda *_: defer.succeed(responses.pop(0))

        d = self.scheduler_service.check_events(100)

        self.assertEqual(self.successResultOf(d), [4, 5])
        self.assertEqual(self.kz_partition.__iter__.call_count, 1)
        self.scheduler_service.log.bind.assert_called_once_with(
            scheduler_run_id='transaction-id', utcnow='utcnow')
        log = self.scheduler_service.log.bind.return_value
        log.msg.assert_called_once_with('Got buckets {buckets}',
                                        buckets=[2, 3], path='/part_path')
        self.assertEqual(self.check_events_in_bucket.mock_calls,
                         [mock.call(log, self.mock_store, 2, 'utcnow', 100),
                          mock.call(log, self.mock_store, 3, 'utcnow', 100)])


class CheckEventsInBucketTests(SchedulerTests):
    """
    Tests for `check_events_in_bucket`
    """

    def setUp(self):
        """
        Mock store.fetch_and_delete and `process_events`
        """
        super(CheckEventsInBucketTests, self).setUp()

        self.returns = [[]]

        def _responses(*args):
            result = self.returns.pop(0)
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.mock_store.fetch_and_delete.side_effect = _responses
        self.process_events = patch(
            self, 'otter.scheduler.process_events',
            side_effect=lambda events, store, log: defer.succeed(len(events)))
        self.log = mock.Mock()

    def test_fetch_called(self):
        """
        `fetch_and_delete` called correctly
        """
        d = check_events_in_bucket(self.log, self.mock_store, 1, 'utcnow', 100)
        self.successResultOf(d)
        self.mock_store.fetch_and_delete.assert_called_once_with(1, 'utcnow', 100)
        self.log.bind.assert_called_once_with(bucket=1)

    def test_no_events(self):
        """
        When no events are fetched, they are not processed
        """
        d = check_events_in_bucket(self.log, self.mock_store, 1, 'utcnow', 100)
        self.successResultOf(d)
        self.process_events.assert_called_once_with([], self.mock_store, self.log.bind())

    def test_events_in_limit(self):
        """
        When events fetched < 100, they are processed
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                   'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(10)]
        self.returns = [events]

        d = check_events_in_bucket(self.log, self.mock_store, 1, 'utcnow', 100)

        self.successResultOf(d)
        # Ensure fetch_and_delete and process_events is called only once
        self.mock_store.fetch_and_delete.assert_called_once_with(1, 'utcnow', 100)
        self.process_events.assert_called_once_with(events, self.mock_store, self.log.bind())

    def test_events_process_error(self):
        """
        error is logged if `process_events` returns error
        """
        self.returns = [ValueError('e')]

        d = check_events_in_bucket(self.log, self.mock_store, 1, 'now', 100)

        self.successResultOf(d)
        self.log.bind.return_value.err.assert_called_once_with(CheckFailure(ValueError))
        self.assertFalse(self.process_events.called)

    def test_events_more_limit(self):
        """
        When events fetched > 100, they are processed in 2 batches
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                    'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(100)]
        events2 = [{'tenantId': '1235', 'groupId': 'scal54', 'policyId': 'pol4{}'.format(i),
                    'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(10)]
        self.returns = [events1, events2]

        d = check_events_in_bucket(self.log, self.mock_store, 1, 'now', 100)

        self.successResultOf(d)
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 2)
        self.assertEqual(self.process_events.mock_calls,
                         [mock.call(events1, self.mock_store, self.log.bind()),
                          mock.call(events2, self.mock_store, self.log.bind())])

    def test_events_batch_error(self):
        """
        When error occurs after first batch of events are processed, then it
        logs errors and does not try to fetch again
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                   'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(100)]
        self.returns = [events, ValueError('some')]

        d = check_events_in_bucket(self.log, self.mock_store, 1, 'now', 100)

        self.successResultOf(d)
        self.log.bind.return_value.err.assert_called_once_with(CheckFailure(ValueError))
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 2)
        self.process_events.assert_called_once_with(events, self.mock_store,
                                                    self.log.bind())

    def test_events_batch_process(self):
        """
        When events fetched > 100, they are processed in batches until all
        events are processed
        """
        events1 = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                    'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(100)]
        events2 = [{'tenantId': '1235', 'groupId': 'scal54', 'policyId': 'pol4{}'.format(i),
                    'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(100)]
        events3 = [{'tenantId': '1236', 'groupId': 'scal64', 'policyId': 'pol4{}'.format(i),
                    'trigger': 'now', 'cron': None, 'bucket': 1} for i in range(10)]
        self.returns = [events1, events2, events3]

        d = check_events_in_bucket(self.log, self.mock_store, 1, 'now', 100)

        self.successResultOf(d)
        self.assertEqual(self.mock_store.fetch_and_delete.mock_calls,
                         [mock.call(1, 'now', 100)] * 3)
        self.assertEqual(self.process_events.mock_calls,
                         [mock.call(events1, self.mock_store, self.log.bind()),
                          mock.call(events2, self.mock_store, self.log.bind()),
                          mock.call(events3, self.mock_store, self.log.bind())])


class ProcessEventsTests(SchedulerTests):
    """
    Tests for `process_events`
    """

    def setUp(self):
        """
        Mock `execute_event` and `add_cron_events`
        """
        super(ProcessEventsTests, self).setUp()
        self.execute_event = patch(self, 'otter.scheduler.execute_event',
                                   return_value=defer.succeed(None))
        self.add_cron_events = patch(
            self, 'otter.scheduler.add_cron_events',
            side_effect=lambda store, log, events, deleted_policy_ids: defer.succeed(events))
        self.log = mock_log()

    def test_no_events(self):
        """
        Does nothing on no events
        """
        process_events([], self.mock_store, self.log)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.execute_event.called)
        self.assertFalse(self.add_cron_events.called)

    def test_success(self):
        """
        Test success path: Logs number of events, calls `execute_event` on each event
        and calls `add_cron_events`
        """
        events = range(10)
        d = process_events(events, self.mock_store, self.log)
        self.assertEqual(self.successResultOf(d), 10)
        self.log.msg.assert_called_once_with('Processing {num_events} events', num_events=10)
        self.assertEqual(
            self.execute_event.mock_calls,
            [mock.call(self.mock_store, self.log, event, set()) for event in events])
        self.add_cron_events.assert_called_once_with(self.mock_store, self.log, events, set())


class AddCronEventsTests(SchedulerTests):
    """
    Tests for `add_cron_events`
    """

    def setUp(self):
        """
        Mock store.add_cron_events and next_cron_occurrence
        """
        super(AddCronEventsTests, self).setUp()
        self.mock_store.add_cron_events.return_value = defer.succeed(None)
        self.next_cron_occurrence = patch(self, 'otter.scheduler.next_cron_occurrence',
                                          return_value='next')
        self.log = mock_log()

    def test_no_events(self):
        """
        Does nothing on no events
        """
        d = add_cron_events(self.mock_store, self.log, [], set())
        self.assertIsNone(d)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.next_cron_occurrence.called)
        self.assertFalse(self.mock_store.add_cron_events.called)

    def test_no_events_to_add(self):
        """
        When all events passed are to be deleted, then does nothing
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                   'trigger': 'now', 'cron': '*', 'bucket': 1} for i in range(3)]
        d = add_cron_events(self.mock_store, self.log, events,
                            set(['pol4{}'.format(i) for i in range(3)]))
        self.assertIsNone(d)
        self.assertFalse(self.log.msg.called)
        self.assertFalse(self.next_cron_occurrence.called)
        self.assertFalse(self.mock_store.add_cron_events.called)

    def test_store_add_cron_called(self):
        """
        Updates cron events for non-deleted policies by calling store.add_cron_events
        """
        events = [{'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol4{}'.format(i),
                   'trigger': 'now', 'cron': '*', 'bucket': 1} for i in range(10)]
        deleted_policy_ids = set(['pol41', 'pol45'])
        new_events = events[:]
        new_events.pop(1)
        new_events.pop(4)
        [event.update({'trigger': 'next'}) for event in new_events]

        d = add_cron_events(self.mock_store, self.log, events, deleted_policy_ids)

        self.assertIsNone(self.successResultOf(d), None)
        self.assertEqual(self.next_cron_occurrence.call_count, 8)
        self.mock_store.add_cron_events.assert_called_once_with(new_events)


class ExecuteEventTests(SchedulerTests):
    """
    Tests for `execute_event`
    """

    def setUp(self):
        """
        Mock execution of scaling policy
        """
        super(ExecuteEventTests, self).setUp()
        self.mock_group = iMock(IScalingGroup)
        self.mock_store.get_scaling_group.return_value = self.mock_group

        # mock out modify state
        self.mock_state = mock.MagicMock(spec=[])  # so nothing can call it
        self.new_state = None

        def _set_new_state(new_state):
            self.new_state = new_state

        def _mock_modify_state(modifier, *args, **kwargs):
            d = modifier(self.mock_group, self.mock_state, *args, **kwargs)
            return d.addCallback(_set_new_state)

        self.mock_group.modify_state.side_effect = _mock_modify_state
        self.maybe_exec_policy = patch(self, 'otter.scheduler.maybe_execute_scaling_policy',
                                       return_value=defer.succeed('newstate'))
        self.log = mock.Mock()
        self.log_args = {'tenant_id': '1234', 'scaling_group_id': 'scal44', 'policy_id': 'pol44'}
        self.event = {'tenantId': '1234', 'groupId': 'scal44', 'policyId': 'pol44',
                      'trigger': 'now', 'cron': '*', 'bucket': 1, 'version': 'v2'}

    def test_event_executed(self):
        """
        Event is executed successfully and appropriate logs logged
        """
        del_pol_ids = set()
        d = execute_event(self.mock_store, self.log, self.event, del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.log.bind.assert_called_with(**self.log_args)
        log = self.log.bind.return_value
        log.msg.assert_called_once_with('Scheduler executing policy {policy_id}')
        self.maybe_exec_policy.assert_called_once_with(
            log, 'transaction-id', self.mock_group, self.mock_state,
            policy_id=self.event['policyId'], version=self.event['version'])
        self.assertTrue(self.mock_group.modify_state.called)
        self.assertEqual(self.new_state, 'newstate')
        self.assertEqual(len(del_pol_ids), 0)

    def test_deleted_group_event(self):
        """
        Executing event whose group has been deleted. It captures policyId in
        deleted_policy_ids and does not call maybe_execute_scaling_policy
        """
        del_pol_ids = set()
        self.mock_group.modify_state.side_effect = lambda *_: defer.fail(NoSuchScalingGroupError(1, 2))

        d = execute_event(self.mock_store, self.log, self.event, del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(del_pol_ids, set(['pol44']))
        self.assertFalse(self.maybe_exec_policy.called)

    def test_deleted_policy_event(self):
        """
        Policy corresponding to the event has deleted. It captures
        policyId in deleted_policy_ids and does not call maybe_execute_scaling_policy
        """
        del_pol_ids = set()
        self.mock_group.modify_state.side_effect = (
            lambda *_: defer.fail(NoSuchPolicyError(1, 2, 3)))

        d = execute_event(self.mock_store, self.log, self.event, del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(del_pol_ids, set(['pol44']))
        self.assertFalse(self.maybe_exec_policy.called)

    def test_semantic_prob(self):
        """
        Policy execution causes semantic error like cooldowns not met.
        i.e. CannotExecutePolicyError is captured and logged
        """
        del_pol_ids = set()
        self.maybe_exec_policy.return_value = defer.fail(CannotExecutePolicyError(*range(4)))

        d = execute_event(self.mock_store, self.log, self.event, del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(len(del_pol_ids), 0)
        self.log.bind.return_value.msg.assert_called_with(
            'Scheduler cannot execute policy {policy_id}',
            reason=CheckFailure(CannotExecutePolicyError))

    def test_unknown_error(self):
        """
        Unknown error occurs. It is logged and not propogated
        """
        del_pol_ids = set()
        self.log.bind.return_value.err.return_value = None
        self.maybe_exec_policy.return_value = defer.fail(ValueError(4))

        d = execute_event(self.mock_store, self.log, self.event, del_pol_ids)

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(len(del_pol_ids), 0)
        self.log.bind.return_value.err.assert_called_with(
            CheckFailure(ValueError), 'Scheduler failed to execute policy {policy_id}')
