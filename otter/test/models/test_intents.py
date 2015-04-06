from effect import Effect
from effect import sync_perform

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.models.intents import (
    GetScalingGroupInfo, ModifyGroupState, get_model_dispatcher)
from otter.models.interface import IScalingGroupCollection
from otter.test.utils import iMock, mock_group, mock_log


class ModifyGroupStateTests(SynchronousTestCase):
    """Tests for :func:`perform_modify_group_state`."""
    def test_perform(self):
        group = mock_group(None)
        mgs = ModifyGroupState(scaling_group=group,
                               modifier=lambda g, o: 'new state')
        dispatcher = get_model_dispatcher(mock_log(), None)
        result = sync_perform(dispatcher, Effect(mgs))
        self.assertIsNone(result)
        self.assertEqual(group.modify_state_values, ['new state'])


class GetScalingGroupInfoTests(SynchronousTestCase):
    """Tests for :obj:`GetScalingGroupInfo`."""
    def test_perform(self):
        """Performing returns the group, the state, and the launch config."""
        def view_manifest(with_policies, with_webhooks):
            self.assertEqual(with_policies, False)
            self.assertEqual(with_webhooks, False)
            return succeed(manifest)

        def get_scaling_group(log, tenant_id, group_id):
            return data[(log, tenant_id, group_id)]

        log = mock_log()
        manifest = {}
        group = mock_group(None)
        group.view_manifest.side_effect = view_manifest
        data = {(log, '00', 'g1'): group}
        store = iMock(IScalingGroupCollection)
        store.get_scaling_group.side_effect = get_scaling_group
        dispatcher = get_model_dispatcher(log, store)
        info = sync_perform(
            dispatcher,
            Effect(GetScalingGroupInfo(tenant_id='00', group_id='g1')))
        self.assertEqual(info, (group, manifest))
