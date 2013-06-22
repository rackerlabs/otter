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
        self.mock_store.fetch_batch_of_events.return_value = defer.succeed([])
        d = check_for_events(self.mock_log, 100)
        result = self.successResultOf(d)
        self.assertEquals(result, None)

    def test_one(self):
        """
        Test with one event
        """
        eventlist = [('1234', 'scal44', 'pol44', 'now')]
        self.mock_store.fetch_batch_of_events.return_value = defer.succeed(eventlist)
        d = check_for_events(self.mock_log, 100)
        result = self.successResultOf(d)
        self.assertEquals(result, None)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '1234', 'scal44')
        self.assertEqual(self.mock_group.modify_state.call_count, 1)

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
        batches = [0]
        mockcalllater = iMock(IReactorTime)
        def _second_time(seconds, functions, *args, **kwargs):
            batches[0] += 1
            self.mock_store.fetch_batch_of_events.return_value = defer.succeed(eventlist)
            if batches[0] == 2:
                self.mock_store.fetch_batch_of_events.return_value = defer.succeed([])
            functions(*args, **kwargs)

        mockcalllater.callLater.side_effect = _second_time

        eventlist = [('1234', 'scal44', 'pol44', 'now') for i in range(100)]
        self.mock_store.fetch_batch_of_events.return_value = defer.succeed(eventlist)
        d = check_for_events(self.mock_log, 100, mockcalllater)
        result = self.successResultOf(d)
        self.assertEquals(result, None)

        self.assertEqual(self.mock_group.modify_state.call_count, 200)
        self.assertEqual(self.mock_controller.maybe_execute_scaling_policy.call_count, 200)
        self.assertEqual(self.mock_store.get_scaling_group.call_count, 200)
        self.assertEqual(mockcalllater.callLater.call_count, 2)
        mockcalllater.callLater.assert_called_with(0, check_for_events, self.mock_log, 100, mockcalllater)

