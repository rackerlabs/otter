"""Tests for convergence."""

from characteristic import attributes

import mock

from effect import Effect, ConstantIntent, parallel, ParallelEffects
from effect.testing import StubIntent, resolve_effect, resolve_stubs

from pyrsistent import pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.util.timestamp import now
from otter.convergence import (
    CreateServer, DeleteServer,
    RemoveFromLoadBalancer, ChangeLoadBalancerNode,
    BulkAddToRCv3, BulkRemoveFromRCv3,
    SetMetadataItemOnServer,
    Request, LBConfig,
    NodeCondition, NodeType,
    _reqs_to_effect,
    execute_convergence, tenant_is_enabled)


class ObjectStorageTests(SynchronousTestCase):
    """
    Tests for objects that store data such as :class:`LBConfig`
    """

    def test_lbconfig_default_weight_condition_and_type(self):
        """
        :obj:`LBConfig` only requires a port.  The other attributes have
        default values.
        """
        lb = LBConfig(port=80)
        self.assertEqual(lb.weight, 1)
        self.assertEqual(lb.condition, NodeCondition.ENABLED)
        self.assertEqual(lb.type, NodeType.PRIMARY)


class StepAsRequestTests(SynchronousTestCase):
    """
    Tests for converting :obj:`IStep` implementations to :obj:`Request`s.
    """

    def test_create_server(self):
        """
        :obj:`CreateServer.as_request` produces a request for creating a server.
        """
        create = CreateServer(launch_config=pmap({'name': 'myserver', 'flavorRef': '1'}))
        self.assertEqual(
            create.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='POST',
                path='servers',
                data=pmap({'name': 'myserver', 'flavorRef': '1'})))

    def test_delete_server(self):
        """
        :obj:`DeleteServer.as_request` produces a request for deleting a server.
        """
        delete = DeleteServer(server_id='abc123')
        self.assertEqual(
            delete.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='DELETE',
                path='servers/abc123'))

    def test_set_metadata_item(self):
        """
        :obj:`SetMetadataItemOnServer.as_request` produces a request for
        setting a metadata item on a particular server.
        """
        meta = SetMetadataItemOnServer(server_id='abc123', key='metadata_key',
                                       value='teapot')
        self.assertEqual(
            meta.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='PUT',
                path='servers/abc123/metadata/metadata_key',
                data={'meta': {'metadata_key': 'teapot'}}))

    def test_remove_from_load_balancer(self):
        """
        :obj:`RemoveFromLoadBalancer.as_request` produces a request for
        removing a node from a load balancer.
        """
        lbremove = RemoveFromLoadBalancer(
            lb_id='abc123',
            node_id='node1')
        self.assertEqual(
            lbremove.as_request(),
            Request(
                service=ServiceType.CLOUD_LOAD_BALANCERS,
                method='DELETE',
                path='loadbalancers/abc123/node1'))

    def test_change_load_balancer_node(self):
        """
        :obj:`ChangeLoadBalancerNode.as_request` produces a request for
        modifying a load balancer node.
        """
        changenode = ChangeLoadBalancerNode(
            lb_id='abc123',
            node_id='node1',
            condition='DRAINING',
            weight=50,
            type="PRIMARY")
        self.assertEqual(
            changenode.as_request(),
            Request(
                service=ServiceType.CLOUD_LOAD_BALANCERS,
                method='PUT',
                path='loadbalancers/abc123/nodes/node1',
                data={'condition': 'DRAINING',
                      'weight': 50}))

    def _generic_bulk_rcv3_step_test(self, step_class, expected_method):
        """
        A generic test for bulk RCv3 steps.

        :param step_class: The step class under test.
        :param str method: The expected HTTP method of the request.
        """
        step = step_class(lb_node_pairs=pset([
            ("lb-1", "node-a"),
            ("lb-1", "node-b"),
            ("lb-1", "node-c"),
            ("lb-1", "node-d"),
            ("lb-2", "node-a"),
            ("lb-2", "node-b"),
            ("lb-3", "node-c"),
            ("lb-3", "node-d")
        ]))
        request = step.as_request()
        self.assertEqual(request.service, ServiceType.RACKCONNECT_V3)
        self.assertEqual(request.method, expected_method)
        self.assertEqual(request.success_codes,
                         (201,) if request.method == "POST" else (204,))
        self.assertEqual(request.path, "load_balancer_pools/nodes")
        self.assertEqual(request.headers, None)

        expected_data = [
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-a'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-b'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-c'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-d'}},
            {'load_balancer_pool': {'id': 'lb-2'},
             'cloud_server': {'id': 'node-a'}},
            {'load_balancer_pool': {'id': 'lb-2'},
             'cloud_server': {'id': 'node-b'}},
            {'load_balancer_pool': {'id': 'lb-3'},
             'cloud_server': {'id': 'node-c'}},
            {'load_balancer_pool': {'id': 'lb-3'},
             'cloud_server': {'id': 'node-d'}}
        ]
        key_fn = lambda e: (e["load_balancer_pool"]["id"], e["cloud_server"]["id"])
        request_data = sorted(request.data, key=key_fn)
        self.assertEqual(request_data, expected_data)

    def test_add_nodes_to_rcv3_load_balancers(self):
        """
        :obj:`BulkAddToRCv3.as_request` produces a request for
        adding any combination of nodes to any combination of RCv3 load
        balancers.
        """
        self._generic_bulk_rcv3_step_test(BulkAddToRCv3, "POST")

    def test_remove_nodes_from_rcv3_load_balancers(self):
        """
        :obj:`BulkRemoveFromRCv3.as_request` produces a request
        for removing any combination of nodes from any combination of RCv3
        load balancers.
        """
        self._generic_bulk_rcv3_step_test(
            BulkRemoveFromRCv3, "DELETE")


@attributes(["service_type", "method", "url", "headers", "data", "success_codes"],
            defaults={"success_codes": (200,)})
class _PureRequestStub(object):
    """
    A bound request stub, suitable for testing.
    """


class RequestsToEffectTests(SynchronousTestCase):
    """
    Tests for converting :class:`Request` into effects.
    """

    def assertCompileTo(self, conv_requests, expected_effects):
        """
        Assert that the given convergence requests compile down to a parallel
        effect comprised of the given effects.
        """
        effect = _reqs_to_effect(_PureRequestStub, conv_requests)
        self.assertEqual(effect, parallel(expected_effects))

    def test_single_request(self):
        """
        A single request is correctly compiled down to an effect.
        """
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever",
                    success_codes=(999,))]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None,
                             success_codes=(999,))]
        self.assertCompileTo(conv_requests, expected_effects)

    def test_multiple_requests(self):
        """
        Multiple requests of the same type are correctly compiled down to an
        effect.
        """
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever"),
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever/something/else",
                    success_codes=(231,))]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None),
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever/something/else",
                             headers=None,
                             data=None,
                             success_codes=(231,))]
        self.assertCompileTo(conv_requests, expected_effects)

    def test_multiple_requests_of_different_type(self):
        """
        Multiple requests of different types are correctly compiled down to
        an effect.
        """
        data_sentinel = object()
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever"),
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever/something/else",
                    success_codes=(231,)),
            Request(service=ServiceType.CLOUD_SERVERS,
                    method="POST",
                    path="/xyzzy",
                    data=data_sentinel)]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None),
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever/something/else",
                             headers=None,
                             data=None,
                             success_codes=(231,)),
            _PureRequestStub(service_type=ServiceType.CLOUD_SERVERS,
                             method="POST",
                             url="/xyzzy",
                             headers=None,
                             data=data_sentinel)]
        self.assertCompileTo(conv_requests, expected_effects)


class ExecConvergenceTests(SynchronousTestCase):
    """
    Tests for :func:`execute_convergence`
    """

    def setUp(self):
        """
        Sample server json
        """
        self.servers = [
            {'id': 'a', 'state': 'ACTIVE', 'created': now(),
             'addresses': {'private': [{'addr': 'ip1', 'version': 4}]}},
            {'id': 'b', 'state': 'ACTIVE', 'created': now(),
             'addresses': {'private': [{'addr': 'ip2', 'version': 4}]}}
        ]

    def test_success(self):
        """
        Executes optimized steps if state of world does not match desired and returns
        True to be called again
        """
        get_servers = lambda r: Effect(StubIntent(ConstantIntent({'gid': self.servers})))
        get_lb = lambda r: Effect(StubIntent(ConstantIntent([])))
        lc = {'args': {'server': {'name': 'test', 'flavorRef': 'f'},
                       'loadBalancers': [{'loadBalancerId': 23, 'port': 80}]}}
        reqfunc = lambda **k: Effect(k)

        eff = execute_convergence(reqfunc, 'gid', 2, lc, get_servers=get_servers,
                                  get_lb=get_lb)

        eff = resolve_stubs(eff)
        # The steps are optimized
        self.assertIsInstance(eff.intent, ParallelEffects)
        self.assertEqual(len(eff.intent.effects), 1)
        self.assertEqual(
            eff.intent.effects[0].intent,
            {'url': 'loadbalancers/23', 'headers': None,
             'service_type': ServiceType.CLOUD_LOAD_BALANCERS,
             'data': {'nodes': mock.ANY},
             'method': 'POST', 'success_codes': (200,)})
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
        get_servers = lambda r: Effect(StubIntent(ConstantIntent({'gid': self.servers})))
        get_lb = lambda r: Effect(StubIntent(ConstantIntent([])))
        lc = {'args': {'server': {'name': 'test', 'flavorRef': 'f'}, 'loadBalancers': []}}
        reqfunc = lambda **k: 1 / 0

        eff = execute_convergence(reqfunc, 'gid', 2, lc, get_servers=get_servers,
                                  get_lb=get_lb)

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
