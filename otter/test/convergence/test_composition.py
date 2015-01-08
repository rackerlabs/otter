"""Tests for convergence."""

import mock

from effect import Effect, ConstantIntent, ParallelEffects
from effect.testing import StubIntent, resolve_effect, resolve_stubs

from pyrsistent import pmap

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.composition import (
    execute_convergence,
    get_desired_group_state,
    json_to_LBConfigs,
    tenant_is_enabled)
from otter.convergence.model import DesiredGroupState, LBConfig, NovaServer, ServerState
from otter.util.pure_http import has_code


class JsonToLBConfigTests(SynchronousTestCase):
    """
    Tests for :func:`json_to_LBConfigs`
    """
    def test_without_rackconnect(self):
        """
        LB config without rackconnect
        """
        self.assertEqual(
            json_to_LBConfigs([{'loadBalancerId': 20, 'port': 80},
                               {'loadBalancerId': 20, 'port': 800},
                               {'loadBalancerId': 21, 'port': 81}]),
            {20: [LBConfig(port=80), LBConfig(port=800)], 21: [LBConfig(port=81)]})

    def test_with_rackconnect(self):
        """
        LB config with rackconnect
        """
        self.assertEqual(
            json_to_LBConfigs([{'loadBalancerId': 20, 'port': 80},
                               {'loadBalancerId': 200, 'type': 'RackConnectV3'},
                               {'loadBalancerId': 21, 'port': 81}]),
            {20: [LBConfig(port=80)], 21: [LBConfig(port=81)]})


class GetDesiredGroupStateTests(SynchronousTestCase):
    """Tests for :func:`get_desired_group_state`."""
    def test_convert(self):
        """An Otter launch config is converted into a :obj:`DesiredGroupState`."""
        server_config = {'name': 'test', 'flavorRef': 'f'}
        lc = {'args': {'server': server_config,
                       'loadBalancers': [{'loadBalancerId': 23, 'port': 80}]}}
        state = get_desired_group_state(lc, 2)
        self.assertEqual(
            state,
            DesiredGroupState(
                launch_config={'server': server_config},
                desired=2,
                desired_lbs={23: [LBConfig(port=80)]}))


class ExecConvergenceTests(SynchronousTestCase):
    """
    Tests for :func:`execute_convergence`
    """

    def setUp(self):
        """
        Sample server json
        """
        self.servers = [
            NovaServer(id='a', state=ServerState.ACTIVE, created=0, servicenet_address='ip1'),
            NovaServer(id='b', state=ServerState.ACTIVE, created=0, servicenet_address='ip2'),
        ]

    def _get_gacd_func(self, servers, group_id, reqfunc):
        def get_all_convergence_data(request_func, grp_id):
            self.assertIs(request_func, reqfunc)
            self.assertEqual(grp_id, group_id)
            return Effect(StubIntent(ConstantIntent((self.servers, []))))
        return get_all_convergence_data

    def test_success(self):
        """
        Executes optimized steps if state of world does not match desired and returns
        True to be called again
        """
        reqfunc = lambda **k: Effect(k)
        get_all_convergence_data = self._get_gacd_func(
            self.servers, 'gid', reqfunc)
        desired = DesiredGroupState(
            launch_config={'server': {'name': 'test', 'flavorRef': 'f'}},
            desired_lbs={23: [LBConfig(port=80)]},
            desired=2)

        eff = execute_convergence(
            reqfunc, 'gid', desired,
            get_all_convergence_data=get_all_convergence_data)

        eff = resolve_stubs(eff)
        # The steps are optimized
        self.assertIsInstance(eff.intent, ParallelEffects)
        self.assertEqual(len(eff.intent.effects), 1)
        self.assertEqual(
            eff.intent.effects[0].intent,
            {'url': 'loadbalancers/23', 'headers': None,
             'service_type': ServiceType.CLOUD_LOAD_BALANCERS,
             'data': {'nodes': mock.ANY},
             'method': 'POST',
             'success_pred': has_code(200)})
        # separate check for nodes as it can be in any order but content is unique
        self.assertEqual(
            set(map(pmap, eff.intent.effects[0].intent['data']['nodes'])),
            set([pmap({'weight': 1, 'type': 'PRIMARY', 'port': 80,
                       'condition': 'ENABLED', 'address': 'ip2'}),
                 pmap({'weight': 1, 'type': 'PRIMARY', 'port': 80,
                       'condition': 'ENABLED', 'address': 'ip1'})]))

        r = resolve_effect(eff, [{'nodes': [{'address': 'ip'}]}])
        # Returns true to be called again
        self.assertIs(r, True)

    def test_no_steps(self):
        """
        If state of world matches desired, no steps are executed and False is returned
        """
        desired = DesiredGroupState(
            launch_config={'server': {'name': 'test', 'flavorRef': 'f'}},
            desired_lbs={},
            desired=2)
        reqfunc = lambda **k: 1 / 0
        get_all_convergence_data = self._get_gacd_func(
            self.servers, 'gid', reqfunc)
        eff = execute_convergence(
            reqfunc, 'gid', desired,
            get_all_convergence_data=get_all_convergence_data)
        self.assertIs(resolve_stubs(eff), False)


class FeatureFlagTest(SynchronousTestCase):
    """
    Tests for determining which tenants should have convergence enabled.
    """

    def test_tenant_is_enabled(self):
        """
        :obj:`convergence.tenant_is_enabled` should return ``True`` when a
        given tenant ID has convergence behavior turned on.
        """
        enabled_tenant_id = "some-tenant"

        def get_config_value(config_key):
            self.assertEqual(config_key, "convergence-tenants")
            return [enabled_tenant_id]
        self.assertEqual(tenant_is_enabled(enabled_tenant_id,
                                           get_config_value),
                         True)

    def test_tenant_is_not_enabled(self):
        """
        :obj:`convergence.tenant_is_enabled` should return ``False`` when a
        given tenant ID has convergence behavior turned off.
        """
        enabled_tenant_id = "some-tenant"

        def get_config_value(config_key):
            self.assertEqual(config_key, "convergence-tenants")
            return [enabled_tenant_id + "-nope"]
        self.assertEqual(tenant_is_enabled(enabled_tenant_id,
                                           get_config_value),
                         False)
