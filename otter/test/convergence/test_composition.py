"""Tests for convergence."""

import json

from pyrsistent import pset

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.composition import (
    get_desired_server_group_state,
    json_to_LBConfigs,
    tenant_is_enabled)
from otter.convergence.model import (
    CLBDescription,
    DesiredServerGroupState,
    RCv3Description
)


class JsonToLBConfigTests(SynchronousTestCase):
    """
    Tests for :func:`json_to_LBConfigs`
    """
    def test_with_clb_and_rackconnect(self):
        """
        LB config with both CLBs and rackconnect.
        """
        self.assertEqual(
            json_to_LBConfigs(
                [{'loadBalancerId': 20, 'port': 80},
                 {'loadBalancerId': 20, 'port': 800},
                 {'loadBalancerId': 20, 'type': 'RackConnectV3'},
                 {'loadBalancerId': 200, 'type': 'RackConnectV3'},
                 {'loadBalancerId': 21, 'port': 81},
                 {'loadBalancerId': 'cebdc220-172f-4b10-9f29-9c7e980ba41d',
                  'type': 'RackConnectV3'}]),
            pset([
                CLBDescription(lb_id='20', port=80),
                CLBDescription(lb_id='20', port=800),
                CLBDescription(lb_id='21', port=81),
                RCv3Description(lb_id='20'),
                RCv3Description(lb_id='200'),
                RCv3Description(lb_id='cebdc220-172f-4b10-9f29-9c7e980ba41d')
            ]))


class GetDesiredServerGroupStateTests(SynchronousTestCase):
    """Tests for :func:`get_desired_server_group_state`."""

    def assert_server_config_hashable(self, state):
        """
        Assert that a :class:`DesiredServerGroupState` has a hashable server
        config.
        """
        try:
            hash(state.server_config)
        except TypeError as e:
            self.fail("{0} in {1}".format(e, state.server_config))

    def test_convert(self):
        """
        An Otter launch config a :obj:`DesiredServerGroupState`, ignoring extra
        config information.
        """
        server_config = {'name': 'test', 'flavorRef': 'f'}
        lc = {'args': {'server': server_config,
                       'loadBalancers': [
                           {'loadBalancerId': 23, 'port': 80,
                            'whatsit': 'invalid'},
                           {'loadBalancerId': 23, 'port': 90},
                           {'loadBalancerId': 23, 'type': 'RackConnectV3'},
                           {'loadBalancerId': '12', 'type': 'RackConnectV3'}],
                       'draining_timeout': 35}}

        expected_server_config = {
            'server': {
                'name': 'test',
                'flavorRef': 'f',
                'metadata': {
                    'rax:auto_scaling_group_id': 'uuid',
                    'rax:autoscale:group:id': 'uuid',
                    'rax:autoscale:lb:CloudLoadBalancer:23': json.dumps(
                        [{"port": 80},
                         {"port": 90}]),
                    'rax:autoscale:lb:RackConnectV3:23': '',
                    'rax:autoscale:lb:RackConnectV3:12': ''
                }
            }
        }
        state = get_desired_server_group_state('uuid', lc, 2)
        self.assertEqual(
            state,
            DesiredServerGroupState(
                server_config=expected_server_config,
                capacity=2,
                desired_lbs=pset([
                    CLBDescription(lb_id='23', port=80),
                    CLBDescription(lb_id='23', port=90),
                    RCv3Description(lb_id='23'),
                    RCv3Description(lb_id='12')]),
                draining_timeout=35.0))
        self.assert_server_config_hashable(state)

    def test_no_lbs(self):
        """
        When no loadBalancers are specified, the returned
        DesiredServerGroupState has an empty mapping for desired_lbs. If no
        draining_timeout is provided, returned DesiredServerGroupState has
        draining_timeout as 0.0
        """
        server_config = {'name': 'test', 'flavorRef': 'f'}
        lc = {'args': {'server': server_config}}

        expected_server_config = {
            'server': {
                'name': 'test',
                'flavorRef': 'f',
                'metadata': {
                    'rax:auto_scaling_group_id': 'uuid',
                    'rax:autoscale:group:id': 'uuid'}}}
        state = get_desired_server_group_state('uuid', lc, 2)
        self.assertEqual(
            state,
            DesiredServerGroupState(
                server_config=expected_server_config,
                capacity=2,
                desired_lbs=pset(),
                draining_timeout=0.0))
        self.assert_server_config_hashable(state)


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

    def test_unconfigured(self):
        """
        When no `convergence-tenants` key is available in the config, False is
        returned.
        """
        self.assertEqual(tenant_is_enabled('foo', lambda x: None), False)
