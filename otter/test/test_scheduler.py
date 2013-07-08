"""
Tests for :mod:`otter.scheduler`
"""

from twisted.trial.unittest import TestCase
from twisted.internet import defer
from twisted.internet.task import Clock

import mock

from silverberg.lock import BusyLockError

from otter.scheduler import SchedulerService
from otter.test.utils import iMock, DeferredTestMixin, patch
from otter.models.interface import IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection
from otter.rest.application import set_store
from otter.models.cass import LOCK_TABLE_NAME


class SchedulerTestCase(DeferredTestMixin, TestCase):
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

        self.mock_store.delete_events.return_value = defer.succeed(None)

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

        self.mock_log = mock.MagicMock()

        self.mock_controller = patch(self, 'otter.scheduler.controller')

        def _mock_with_lock(lock, func, *args, **kwargs):
            return defer.maybeDeferred(func, *args, **kwargs)

        self.mock_lock = patch(self, 'otter.scheduler.BasicLock')
        self.mock_with_lock = patch(self, 'otter.scheduler.with_lock')
        self.mock_with_lock.side_effect = _mock_with_lock
        self.slv_client = mock.MagicMock()

        self.clock = Clock()
        self.scheduler_service = SchedulerService(100, 1, self.slv_client, self.clock)

    def validate_calls(self, d, fetch_call_count, events):
        """
        Validate all the calls made in the service w.r.t to the events
        """
        num_events = len(events)
        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, fetch_call_count)
        self.assertEqual(self.mock_group.modify_state.call_count, num_events)
        self.assertEqual(self.mock_store.get_scaling_group.call_args_list,
                         [mock.call(mock.ANY, tid, gid) for tid, gid, pid, t in events])
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.mock_calls,
                         [mock.call(mock.ANY, 'transaction-id', self.mock_group,
                          self.mock_state, policy_id=policy_id)
                         for tid, gid, policy_id, t in events])

    def test_empty(self):
        """
        No policies are executed when ``fetch_batch_of_events`` return empty list
        i.e. no events are there before now
        """
        self.returns = [[]]
        d = self.scheduler_service.check_for_events(100)
        self.validate_calls(d, 1, [])

    def test_one(self):
        """
        policy is executed when its corresponding event is there before now
        """
        events = [('1234', 'scal44', 'pol44', 'now')]
        self.returns = [events]

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, 1, events)

    def test_many(self):
        """
        Events are fetched and processed as batches of 100. Its corresponding policies
        are executed.
        """
        events1 = [('1234', 'scal44', 'pol44', 'now') for i in range(100)]
        events2 = [('1234', 'scal44', 'pol45', 'now') for i in range(100)]
        self.returns = [events1, events2, []]

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, 3, events1 + events2)

    def test_timer_works(self):
        """
        The scheduler executes every x seconds
        """
        events1 = [('1234', 'scal44', 'pol44', 'now') for i in range(10)]
        events2 = [('1234', 'scal44', 'pol45', 'now') for i in range(20)]
        self.returns = [events1, events2]

        # events not fetched before startService
        self.validate_calls(defer.succeed(None), 0, [])

        # events fetched after calling startService
        self.scheduler_service.startService()
        self.validate_calls(defer.succeed(None), 1, events1)

        # events are fetched again after timer expires
        self.clock.advance(1)
        self.validate_calls(defer.succeed(None), 2, events1 + events2)

    def test_called_with_lock(self):
        """
        ``fetch_and_process`` is called with a lock
        """
        events1 = [('1234', 'scal44', 'pol44', 'now') for i in range(100)]
        events2 = [('1234', 'scal44', 'pol45', 'now') for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, 2, events1 + events2)

        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.call_count, 2)
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)] * 2)

    def test_does_nothing_on_no_lock(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock. It
        does not call ``fetch_and_process``
        """
        events1 = [('1234', 'scal44', 'pol44', 'now') for i in range(100)]
        events2 = [('1234', 'scal44', 'pol45', 'now') for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        with_lock_impl = lambda *args: defer.fail(BusyLockError(LOCK_TABLE_NAME, 'schedule'))
        self.mock_with_lock.side_effect = with_lock_impl

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, 0, [])
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)])

    def test_does_nothing_on_no_lock_second_time(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock after
        finishing first batch of 100 events. It does not call ``fetch_and_process`` second time
        """
        events1 = [('1234', 'scal44', 'pol44', 'now') for i in range(100)]
        events2 = [('1234', 'scal44', 'pol45', 'now') for i in range(20)]
        self.returns = [events1, events2]

        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        _with_lock_first_time = [True]

        def _with_lock(lock, func, *args, **kwargs):
            if _with_lock_first_time[0]:
                _with_lock_first_time[0] = False
                return defer.maybeDeferred(func, *args, **kwargs)
            raise BusyLockError(LOCK_TABLE_NAME, 'schedule')

        self.mock_with_lock.side_effect = _with_lock

        d = self.scheduler_service.check_for_events(100)

        self.validate_calls(d, 1, events1)
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)] * 2)
