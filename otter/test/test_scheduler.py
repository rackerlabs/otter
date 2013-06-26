""" CQL Batch wrapper test """
from twisted.trial.unittest import TestCase
from otter.scheduler import check_for_events
from otter.test.utils import iMock, DeferredTestMixin, patch
from otter.models.interface import IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection
from otter.rest.application import set_store
from twisted.internet import defer
import mock
from twisted.internet.interfaces import IReactorTime


class SchedulerTestCase(DeferredTestMixin, TestCase):
    """
    Test the scheduler
    """

    def setUp(self):
        """
        setup
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

        controller_patcher = mock.patch('otter.scheduler.controller')
        self.mock_controller = controller_patcher.start()
        self.addCleanup(controller_patcher.stop)

    def test_empty(self):
        """
        Test what happens when you launch it with no events
        """
        self.returns = [[]]
        d = check_for_events(self.mock_log, 100)
        result = self.successResultOf(d)
        self.assertEqual(self.mock_store.delete_events.call_count, 0)
        self.assertEquals(result, None)

    def test_one(self):
        """
        Test with one event
        """
        self.returns = [[('1234', 'scal44', 'pol44', 'now')]]
        d = check_for_events(self.mock_log, 100)
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
        Test with many events
        """
        deferLater_patcher = mock.patch('otter.scheduler.task.deferLater')
        deferLater = deferLater_patcher.start()
        self.addCleanup(deferLater_patcher.stop)
        mockcalllater = iMock(IReactorTime)

        self.returns = [[('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        [('1234', 'scal44', 'pol44', 'now') for i in range(100)],
                        []]

        def _second_time(clock, seconds, functions, *args, **kwargs):
            functions(*args, **kwargs)

        deferLater.side_effect = _second_time

        d = check_for_events(self.mock_log, 100, mockcalllater)
        result = self.successResultOf(d)
        self.assertEquals(result, None)

        self.assertEqual(self.mock_group.modify_state.call_count, 200)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 200)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 200)
        self.assertEqual(deferLater.call_count, 2)
        self.assertEqual(self.mock_store.delete_events.call_count, 2)
        self.mock_store.delete_events.assert_called_with(['pol44' for i in range(100)])
        deferLater.assert_called_with(mockcalllater, 0, check_for_events,
                                      self.mock_log, 100, mockcalllater)
