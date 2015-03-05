from effect import Effect, TypeDispatcher
from effect import sync_perform

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.models.intents import (
    GetScalingGroupInfo, ModifyGroupState,
    get_cassandra_dispatcher,
    perform_modify_group_state)
from otter.test.utils import mock_group, mock_log


class ModifyGroupStateTests(SynchronousTestCase):
    """Tests for :func:`perform_modify_group_state`."""
    def test_perform(self):
        group = mock_group(None)
        mgs = ModifyGroupState(scaling_group=group,
                               modifier=lambda g, o: 'new state')
        dispatcher = TypeDispatcher({
            ModifyGroupState: perform_modify_group_state})
        result = sync_perform(dispatcher, Effect(mgs))
        self.assertEqual(result, 'new state')
        self.assertEqual(group.modify_state_values, ['new state'])


class GetScalingGroupInfoTests(SynchronousTestCase):
    """Tests for :obj:`GetScalingGroupInfo`."""
    def test_perform(self):
        """Performing returns the group, the state, and the launch config."""
        log = mock_log()
        state = object()
        lc = object()
        group = mock_group(state)
        group.view_state.return_value = succeed(state)
        group.view_launch_config.return_value = succeed(lc)

        data = {('00', 'g1'): group}

        class Store(object):
            def get_scaling_group(s_self, _log, tenant_id, group_id):
                self.assertEqual(_log, log)
                return data[(tenant_id, group_id)]

        store = Store()
        dispatcher = get_cassandra_dispatcher(log, store)
        info = sync_perform(
            dispatcher,
            Effect(GetScalingGroupInfo(tenant_id='00', group_id='g1')))
        self.assertEqual(info, (group, state, lc))
