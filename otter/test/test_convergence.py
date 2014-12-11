"""Tests for convergence."""

import calendar
from functools import partial

from characteristic import attributes

import mock

from effect import Effect, ConstantIntent, parallel, ParallelEffects
from effect.testing import StubIntent, resolve_effect, resolve_stubs

from pyrsistent import pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.util.retry import ShouldDelayAndRetry, exponential_backoff_interval, retry_times
from otter.test.utils import patch, resolve_retry_stubs
from otter.util.timestamp import from_timestamp, now
from otter.convergence import (
    get_all_server_details, get_scaling_group_servers,
    CreateServer, DeleteServer,
    RemoveFromLoadBalancer, ChangeLoadBalancerNode,
    BulkAddToRCv3, BulkRemoveFromRCv3,
    SetMetadataItemOnServer,
    NovaServer, Request, LBConfig, LBNode,
    ServerState, ServiceType, NodeCondition, NodeType,
    extract_drained_at, get_load_balancer_contents, _reqs_to_effect,
    execute_convergence, to_nova_server, json_to_LBConfigs, tenant_is_enabled)


def _request(requests):
    def request(service_type, method, url):
        response = requests.get((service_type, method, url))
        if response is None:
            raise KeyError("{} not in {}".format((method, url), requests.keys()))
        return Effect(StubIntent(ConstantIntent(response)))
    return request


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail?limit=10')
        self.servers = [{'id': i} for i in range(9)]

    def test_get_all_less_batch_size(self):
        """
        `get_all_server_details` will not fetch again if first get returns
        results with size < batch_size
        """
        request = _request({self.req: {'servers': self.servers}})
        eff = get_all_server_details(request, batch_size=10)
        result = resolve_retry_stubs(eff)
        self.assertEqual(result, self.servers)

    def test_get_all_above_batch_size(self):
        """
        `get_all_server_details` will fetch again until batch returned has
        size < batch_size
        """
        servers = [{'id': i} for i in range(19)]

        req2 = (ServiceType.CLOUD_SERVERS, 'GET',
                'servers/detail?limit=10&marker=9')
        request = _request({self.req: {'servers': servers[:10]},
                            req2: {'servers': servers[10:]}})
        eff = get_all_server_details(request, batch_size=10)
        self.assertEqual(resolve_retry_stubs(resolve_retry_stubs(eff)), servers)

    def test_retry(self):
        """The HTTP requests are retried with some appropriate policy."""
        request = _request({self.req: {'servers': self.servers}})
        eff = get_all_server_details(request, batch_size=10)
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))
        result = resolve_retry_stubs(eff)
        self.assertEqual(result, self.servers)


class GetScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_scaling_group_servers`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail?limit=100')

    def test_filters_no_metadata(self):
        """
        Servers without metadata are not included in the result.
        """
        servers = [{'id': i} for i in range(10)]
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(resolve_retry_stubs(eff), {})

    def test_filters_no_as_metadata(self):
        """
        Does not include servers which have metadata but does not have AS info in it
        """
        servers = [{'id': i, 'metadata': {}} for i in range(10)]
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(resolve_retry_stubs(eff), {})

    def test_returns_as_servers(self):
        """
        Returns servers with AS metadata in it grouped by scaling group ID
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': 10}])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(
            resolve_retry_stubs(eff),
            {'a': as_servers[:5] + [as_servers[-1]], 'b': as_servers[5:8]})

    def test_filters_on_user_criteria(self):
        """
        Considers user provided filter if provided
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request, server_predicate=lambda s: s['id'] % 3 == 0)
        self.assertEqual(
            resolve_retry_stubs(eff),
            {'a': [as_servers[0], as_servers[3]], 'b': [as_servers[6]]})


class ExtractDrainedTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.extract_drained_at`
    """
    summary = ("Node successfully updated with address: " +
               "'10.23.45.6', port: '8080', weight: '1', condition: 'DRAINING'")
    updated = '2014-10-23T18:10:48.000Z'
    feed = ('<feed xmlns="http://www.w3.org/2005/Atom">' +
            '<entry><summary>{}</summary><updated>{}</updated></entry>' +
            '<entry><summary>else</summary><updated>badtime</updated></entry>' +
            '</feed>')

    def test_first_entry(self):
        """
        Takes the first entry only
        """
        feed = self.feed.format(self.summary, self.updated)
        self.assertEqual(extract_drained_at(feed),
                         calendar.timegm(from_timestamp(self.updated).utctimetuple()))

    def test_invalid_first_entry(self):
        """
        Raises error if first entry is not DRAINING entry
        """
        feed = self.feed.format("Node successfully updated with ENABLED", self.updated)
        self.assertRaises(ValueError, extract_drained_at, feed)


class GetLBContentsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.get_load_balancer_contents`
    """

    def setUp(self):
        """
        Stub request function and mock `extract_drained_at`
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): [{'id': 1}, {'id': 2}],
            ('GET', 'loadbalancers/1/nodes', True): [
                {'id': '11', 'port': 20, 'address': 'a11',
                 'weight': 2, 'condition': 'DRAINING', 'type': 'PRIMARY'},
                {'id': '12', 'port': 20, 'address': 'a12',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}],
            ('GET', 'loadbalancers/2/nodes', True): [
                {'id': '21', 'port': 20, 'address': 'a21',
                 'weight': 3, 'condition': 'ENABLED', 'type': 'PRIMARY'},
                {'id': '22', 'port': 20, 'address': 'a22',
                 'weight': 3, 'condition': 'DRAINING', 'type': 'PRIMARY'}],
            ('GET', 'loadbalancers/1/nodes/11.atom', False): '11feed',
            ('GET', 'loadbalancers/2/nodes/22.atom', False): '22feed'
        }
        self.feeds = {'11feed': 1.0, '22feed': 2.0}
        self.mock_eda = patch(
            self, 'otter.convergence.gathering.extract_drained_at',
            side_effect=lambda f: self.feeds[f])

    def _request(self):
        def request(service_type, method, url, json_response=False):
            assert service_type is ServiceType.CLOUD_LOAD_BALANCERS
            response = self.reqs[(method, url, json_response)]
            return Effect(StubIntent(ConstantIntent(response)))
        return request

    def _resolve_retry_stubs(self, eff):
        """
        Like :func:`resolve_retry_stub`, but assert what we expect to be the
        correct policy.
        """
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))
        return resolve_retry_stubs(eff)

    def _resolve_lb(self, eff):
        """Resolve the tree of effects used to fetch LB information."""
        # first resolve the request to list LBs
        lb_nodes_fetch = self._resolve_retry_stubs(eff)
        # which results in a parallel fetch of all nodes from all LBs
        feed_fetches = resolve_effect(
            lb_nodes_fetch,
            map(self._resolve_retry_stubs, lb_nodes_fetch.intent.effects))
        # which results in a list parallel fetch of feeds for the nodes
        lbnodes = resolve_effect(
            feed_fetches,
            map(self._resolve_retry_stubs, feed_fetches.intent.effects))
        # and we finally have the LBNodes.
        return lbnodes

    def test_success(self):
        """
        Gets LB contents with drained_at correctly
        """
        eff = get_load_balancer_contents(self._request())
        draining, enabled = NodeCondition.DRAINING, NodeCondition.ENABLED
        make_config = partial(LBConfig, port=20, type=NodeType.PRIMARY)
        self.assertEqual(
            self._resolve_lb(eff),
            [LBNode(lb_id=1, node_id='11', address='a11', drained_at=1.0,
                    config=make_config(weight=2, condition=draining)),
             LBNode(lb_id=1, node_id='12', address='a12',
                    config=make_config(weight=2, condition=enabled)),
             LBNode(lb_id=2, node_id='21', address='a21',
                    config=make_config(weight=3, condition=enabled)),
             LBNode(lb_id=2, node_id='22', address='a22', drained_at=2.0,
                    config=make_config(weight=3, condition=draining))])

    def test_no_lb(self):
        """
        Return empty list if there are no LB
        """
        self.reqs = {('GET', 'loadbalancers', True): []}
        eff = get_load_balancer_contents(self._request())
        self.assertEqual(self._resolve_lb(eff), [])

    def test_no_nodes(self):
        """
        Return empty if there are LBs but no nodes in them
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): [{'id': 1}, {'id': 2}],
            ('GET', 'loadbalancers/1/nodes', True): [],
            ('GET', 'loadbalancers/2/nodes', True): []
        }
        eff = get_load_balancer_contents(self._request())
        self.assertEqual(self._resolve_lb(eff), [])

    def test_no_draining(self):
        """
        Doesnt fetch feeds if all nodes are ENABLED
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): [{'id': 1}, {'id': 2}],
            ('GET', 'loadbalancers/1/nodes', True): [
                {'id': '11', 'port': 20, 'address': 'a11',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ],
            ('GET', 'loadbalancers/2/nodes', True): [
                {'id': '21', 'port': 20, 'address': 'a21',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ]
        }
        config = LBConfig(port=20, weight=2, condition=NodeCondition.ENABLED,
                          type=NodeType.PRIMARY)
        eff = get_load_balancer_contents(self._request())
        self.assertEqual(
            self._resolve_lb(eff),
            [LBNode(lb_id=1, node_id='11', address='a11', config=config),
             LBNode(lb_id=2, node_id='21', address='a21', config=config)])


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


class ToNovaServerTests(SynchronousTestCase):
    """
    Tests for :func:`to_nova_server`
    """
    def setUp(self):
        """
        Sample servers
        """
        self.createds = [('2020-10-10T10:00:00Z', 1602324000),
                         ('2020-10-20T11:30:00Z', 1603193400)]
        self.servers = [{'id': 'a', 'state': 'ACTIVE', 'created': self.createds[0][0]},
                        {'id': 'b', 'state': 'BUILD', 'created': self.createds[1][0],
                         'addresses': {'private': [{'addr': 'ipv4', 'version': 4}]}}]

    def test_without_address(self):
        """
        Handles server json that does not have "addresses" in it
        """
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a', state=ServerState.ACTIVE, created=self.createds[0][1],
                       servicenet_address=''))

    def test_without_private(self):
        """
        Creates server that does not have private/servicenet IP in it
        """
        self.servers[0]['addresses'] = {'public': 'p'}
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a', state=ServerState.ACTIVE, created=self.createds[0][1],
                       servicenet_address=''))

    def test_with_servicenet(self):
        """
        Create server that has servicenet IP in it
        """
        self.assertEqual(
            to_nova_server(self.servers[1]),
            NovaServer(id='b', state=ServerState.BUILD, created=self.createds[1][1],
                       servicenet_address='ipv4'))


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
