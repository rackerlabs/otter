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

    def test_empty(self):
        """
        No policies are executed when ``fetch_batch_of_events`` return empty list
        i.e. no events are there before now
        """
        self.returns = [[]]
        d = self.scheduler_service.check_for_events(100)
        result = self.successResultOf(d)
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 1)
        self.assertEqual(self.mock_store.delete_events.call_count, 0)
        self.assertEquals(result, None)

    def test_one(self):
        """
        policy is executed when its corresponding event is there before now
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now')]]
        d = self.scheduler_service.check_for_events(100)
        result = self.successResultOf(d)
        self.assertEquals(result, None)

        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 1)
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '1234', 'scal44')
        self.assertEqual(self.mock_group.modify_state.call_count, 1)
        self.mock_store.delete_events.assert_called_once_with(['pol44'])

        self.mock_controller.maybe_execute_scaling_policy.assert_called_once_with(
            mock.ANY,
            'transaction-id',
            self.mock_group,
            self.mock_state,
            policy_id='pol44'
        )

    def test_many(self):
        """
        Events are fetched and processed as batches of 100. Its corresponding policies
        are executed.
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(100)],
                        []]
        d = self.scheduler_service.check_for_events(100)
        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 3)
        self.assertEqual(self.mock_group.modify_state.call_count, 200)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 200)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 200)
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 3)
        self.assertEqual(self.mock_store.delete_events.call_count, 2)
        self.assertEqual(self.mock_store.delete_events.mock_calls,
                         [mock.call(['pol44' for i in range(100)]),
                          mock.call(['pol45' for i in range(100)])])

    def test_timer_works(self):
        """
        The scheduler executes every x seconds
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(10)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(20)]]
        # events not fetched before startService
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 0)
        self.scheduler_service.startService()
        # events fetched after calling startService
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 1)
        self.clock.advance(1)
        # events are fetched again after timer expires
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 2)
        self.assertEqual(self.mock_group.modify_state.call_count, 30)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 30)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 30)
        self.assertEqual(self.mock_store.delete_events.call_count, 2)
        self.assertEqual(self.mock_store.delete_events.mock_calls,
                         [mock.call(['pol44' for i in range(10)]),
                          mock.call(['pol45' for i in range(20)])])

    def test_called_with_lock(self):
        """
        ``fetch_and_process`` is called with a lock
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(20)]]
        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        d = self.scheduler_service.check_for_events(100)

        self.assertIsNone(self.successResultOf(d))
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.call_count, 2)
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)] * 2)
        self.assertEqual(self.mock_group.modify_state.call_count, 120)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 120)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 120)
        self.assertEqual(self.mock_store.delete_events.call_count, 2)
        self.assertEqual(self.mock_store.delete_events.mock_calls,
                         [mock.call(['pol44' for i in range(100)]),
                          mock.call(['pol45' for i in range(20)])])

    def test_does_nothing_on_no_lock(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock. It
        does not call ``fetch_and_process``
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(20)]]
        self.mock_lock.assert_called_once_with(self.slv_client, LOCK_TABLE_NAME, 'schedule',
                                               max_retry=0)

        with_lock_impl = lambda *args: defer.fail(BusyLockError(LOCK_TABLE_NAME, 'schedule'))
        self.mock_with_lock.side_effect = with_lock_impl

        d = self.scheduler_service.check_for_events(100)

        self.assertIsNone(self.successResultOf(d))
        lock = self.mock_lock.return_value
        self.assertEqual(self.mock_with_lock.call_count, 1)
        self.assertEqual(self.mock_with_lock.mock_calls,
                         [mock.call(lock, self.scheduler_service.fetch_and_process, 100)])
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 0)
        self.assertEqual(self.mock_group.modify_state.call_count, 0)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 0)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 0)
        self.assertEqual(self.mock_store.delete_events.call_count, 0)

    def test_does_nothing_on_no_lock_second_time(self):
        """
        ``check_for_events`` gracefully does nothing when it does not get a lock after
        finishing first batch of 100 events. It does not call ``fetch_and_process`` second time
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(20)]]
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

        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_with_lock.call_count, 2)
        self.assertEqual(self.mock_store.fetch_batch_of_events.call_count, 1)
        self.assertEqual(self.mock_group.modify_state.call_count, 100)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 100)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 100)
        self.assertEqual(self.mock_store.delete_events.call_count, 1)
