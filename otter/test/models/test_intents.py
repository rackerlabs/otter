from effect import Effect
from effect import sync_perform

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.models.intents import (
    DeleteGroup, GetScalingGroupInfo, ModifyGroupState, get_model_dispatcher)
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


class ScalingGroupIntentsTests(SynchronousTestCase):
    """
    Tests for :obj:`GetScalingGroupInfo` and `DeleteGroup`
    """

    def setUp(self):
        """
        Sample group, collection and dispatcher
        """
        self.log = mock_log()
        self.group = mock_group(None)
        self.store = iMock(IScalingGroupCollection)
        self.dispatcher = get_model_dispatcher(self.log, self.store)

        def get_scaling_group(log, tenant_id, group_id):
            return self.data[(log, tenant_id, group_id)]

        self.store.get_scaling_group.side_effect = get_scaling_group

    def test_get_scaling_group_info(self):
        """
        Performing `GetScalingGroupInfo` returns the group,
        the state, and the launch config.
        """
        def view_manifest(with_policies, with_webhooks, get_deleting):
            self.assertEqual(with_policies, False)
            self.assertEqual(with_webhooks, False)
            self.assertEqual(get_deleting, True)
            return succeed(manifest)

        manifest = {}
        self.group.view_manifest.side_effect = view_manifest
        self.data = {(self.log, '00', 'g1'): self.group}
        info = sync_perform(
            self.dispatcher,
            Effect(GetScalingGroupInfo(tenant_id='00', group_id='g1')))
        self.assertEqual(info, (self.group, manifest))

    def test_delete_group(self):
        """
        Performing `DeleteGroup` calls group.delete_group
        """
        self.data = {(self.log, '00', 'g1'): self.group}
        self.group.delete_group.return_value = succeed('del')
        self.assertEqual(
            sync_perform(
                self.dispatcher,
                Effect(DeleteGroup(tenant_id='00', group_id='g1'))),
            'del')
