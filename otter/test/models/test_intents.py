from datetime import datetime

from effect import ComposedDispatcher, Effect, TypeDispatcher, sync_performer
from effect import sync_perform

import mock

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.log.intents import get_log_dispatcher
from otter.models.intents import (
    DeleteGroup, GetScalingGroupInfo, ModifyGroupStatePaused,
    UpdateGroupErrorReasons, UpdateGroupStatus, LoadAndUpdateGroupStatus,
    UpdateServersCache, get_model_dispatcher)
from otter.models.interface import (
    GroupState, IScalingGroupCollection, ScalingGroupStatus)
from otter.test.utils import (
    EffectServersCache, IsBoundWith, iMock, matches, mock_group, mock_log)


class ScalingGroupIntentsTests(SynchronousTestCase):
    """
    Tests for :obj:`GetScalingGroupInfo` and `DeleteGroup`
    """

    def setUp(self):
        """
        Sample group, collection and dispatcher
        """
        self.log = mock_log().bind(base_log=True)
        self.state = GroupState('tid', 'gid', 'g', {}, {}, None, {}, True,
                                ScalingGroupStatus.ACTIVE)
        self.group = mock_group(self.state)

    def get_dispatcher(self, store):
        return get_model_dispatcher(self.log, store)

    def get_store(self):
        return iMock(IScalingGroupCollection)

    def perform_with_group(self, eff, expected_lookup, group,
                           fallback_dispatcher=None):
        """Run an effect that will look up group info."""
        def gsg(log, tenant_id, group_id):
            assert (log, tenant_id, group_id) == expected_lookup
            return group
        store = self.get_store()
        store.get_scaling_group.side_effect = gsg
        dispatcher = self.get_dispatcher(store)
        if fallback_dispatcher is not None:
            dispatcher = ComposedDispatcher([dispatcher,
                                             fallback_dispatcher])
        return sync_perform(dispatcher, eff)

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
        info = self.perform_with_group(
            Effect(GetScalingGroupInfo(tenant_id='00', group_id='g1')),
            (self.log, '00', 'g1'), self.group)
        self.assertEqual(info, (self.group, manifest))

    def test_get_scaling_group_info_log_context(self):
        """
        When run in an effectful log context, the fields are bound to the log
        passed to delete_group.
        """
        manifest = {}

        def view_manifest(with_policies, with_webhooks, get_deleting):
            return manifest
        self.group.view_manifest.side_effect = view_manifest
        eff = Effect(GetScalingGroupInfo(tenant_id='00', group_id='g1'))
        expected_lookup = (matches(IsBoundWith(base_log=True, effectful=True)),
                           '00', 'g1')
        result = self.perform_with_group(
            eff, expected_lookup, self.group,
            fallback_dispatcher=get_log_dispatcher(self.log,
                                                   {'effectful': True}))
        self.assertEqual(result, (self.group, manifest))

    def test_delete_group(self):
        """
        Performing `DeleteGroup` calls group.delete_group
        """
        self.group.delete_group.return_value = succeed('del')
        result = self.perform_with_group(
            Effect(DeleteGroup(tenant_id='00', group_id='g1')),
            (self.log, '00', 'g1'), self.group)
        self.assertEqual(result, 'del')

    def test_delete_group_log_context(self):
        """
        When run in an effectful log context, the fields are bound to the log
        passed to get_scaling_group.
        """
        self.group.delete_group.return_value = succeed('del')
        expected_lookup = (matches(IsBoundWith(base_log=True, effectful=True)),
                           '00', 'g1')
        result = self.perform_with_group(
            Effect(DeleteGroup(tenant_id='00', group_id='g1')),
            expected_lookup, self.group,
            fallback_dispatcher=get_log_dispatcher(self.log,
                                                   {'effectful': True}))
        self.assertEqual(result, 'del')

    def test_update_group_status(self):
        """Performing :obj:`UpdateGroupStatus` invokes group.update_status."""
        eff = Effect(UpdateGroupStatus(scaling_group=self.group,
                                       status=ScalingGroupStatus.ERROR))
        self.group.update_status.return_value = None
        self.assertIs(
            sync_perform(self.get_dispatcher(self.get_store()), eff),
            None)
        self.group.update_status.assert_called_once_with(
            ScalingGroupStatus.ERROR)

    def test_update_scaling_group_status(self):
        """
        Performing :obj:`LoadAndUpdateGroupStatus` calls update_status
        on group created from tenant_id and group_id in the object
        """
        eff = Effect(
            LoadAndUpdateGroupStatus("t", "g", ScalingGroupStatus.ERROR))
        self.group.update_status.return_value = None
        result = self.perform_with_group(
            eff, (self.log, 't', 'g'), self.group)
        self.assertIsNone(result)
        self.group.update_status.assert_called_once_with(
            ScalingGroupStatus.ERROR)

    @mock.patch('otter.models.intents.CassScalingGroupServersCache',
                new=EffectServersCache)
    def test_perform_update_servers_cache(self):
        """
        Performing :obj:`UpdateServersCache` updates using
        CassScalingGroupServersCache
        """
        dt = datetime(1970, 1, 1)
        eff = Effect(UpdateServersCache('tid', 'gid', dt, [{'id': 'a'}]))

        @sync_performer
        def perform_update_tuple(disp, intent):
            self.assertEqual(
                intent,
                ('cacheistidgid', dt, [{'id': 'a'}], True))

        disp = ComposedDispatcher([
            TypeDispatcher({tuple: perform_update_tuple}),
            self.get_dispatcher(self.get_store())])
        self.assertIsNone(sync_perform(disp, eff))

    def test_perform_update_error_reasons(self):
        """
        Performing :obj:`UpdateGroupErrorReasons` calls `update_error_reasons`
        """
        self.group.update_error_reasons.return_value = None
        intent = UpdateGroupErrorReasons(self.group, ['r1', 'r2'])
        dispatcher = self.get_dispatcher(self.get_store())
        self.assertIsNone(sync_perform(dispatcher, Effect(intent)))
        self.group.update_error_reasons.assert_called_once_with(['r1', 'r2'])

    def test_modify_group_state_paused(self):
        dispatcher = self.get_dispatcher(self.get_store())
        r = sync_perform(dispatcher,
                         Effect(ModifyGroupStatePaused(self.group, False)))
        self.assertIsNone(r)
        # Returned state has updated paused
        modified_state = self.group.modify_state_values[-1]
        # Returned state object is different than original
        self.assertIsNot(self.state, modified_state)
        # Nothing else is modified
        self.assertEqual(modified_state.paused, False)
        modified_state.paused = True
        self.assertEqual(self.state, modified_state)
