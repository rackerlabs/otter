"""
Tests for :mod:`otter.scheduler`
"""

from twisted.trial.unittest import TestCase
from twisted.internet import defer
from twisted.internet.task import Clock

import mock

from otter.scheduler import SchedulerService
from otter.test.utils import iMock, DeferredTestMixin, patch
from otter.models.interface import IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection
from otter.rest.application import set_store


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

        # Tribal knowledge: When you are returning a defer that succeeds, you
        # need to return it as a side effect instead of just a return value.
        self.mock_store.delete_events.side_effect = lambda _: defer.succeed(None)

        self.mock_generate_transaction_id = patch(
            self, 'otter.scheduler.generate_transaction_id',
            return_value='transaction-id')
        set_store(self.mock_store)

        # mock out modify state
        self.mock_state = mock.MagicMock(spec=[])  # so nothing can call it

        def _mock_modify_state(modifier, *args, **kwargs):
            modifier(self.mock_group, self.mock_state, *args, **kwargs)
            return defer.succeed(None)

        self.mock_group.modify_state.side_effect = _mock_modify_state

        self.mock_log = mock.MagicMock()

        self.mock_controller = patch(self, 'otter.scheduler.controller')

        self.clock = Clock()
        self.scheduler_service = SchedulerService(100, 1, self.clock)

    def test_empty(self):
        """
        No policies are executed when empty no events are there before now
        """
        self.returns = [[]]
        d = self.scheduler_service.check_for_events(100)
        result = self.successResultOf(d)
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
        All polices whose event is there before now is executed
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol45', 'now') for i in range(100)],
                        []]

        d = self.scheduler_service.check_for_events(100)
        self.assertIsNone(self.successResultOf(d))
        self.assertEqual(self.mock_group.modify_state.call_count, 200)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 200)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 200)
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
        self.scheduler_service.startService()
        self.clock.advance(1)
        self.assertEqual(self.mock_group.modify_state.call_count, 30)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 30)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 30)
        self.assertEqual(self.mock_store.delete_events.call_count, 2)
        self.assertEqual(self.mock_store.delete_events.mock_calls,
                         [mock.call(['pol44' for i in range(10)]),
                          mock.call(['pol45' for i in range(20)])])
