"""Tests for convergence gathering."""

import calendar
from functools import partial

from effect import Effect, ConstantIntent
from effect.testing import StubIntent, resolve_effect

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.gathering import (
    extract_drained_at,
    get_all_server_details,
    get_load_balancer_contents,
    get_scaling_group_servers,
    json_to_LBConfigs,
    to_nova_server,
    _private_ipv4_addresses)
from otter.convergence.model import (
    LBConfig,
    LBNode,
    NodeCondition,
    NodeType,
    NovaServer,
    ServerState)
from otter.test.utils import patch, resolve_retry_stubs
from otter.util.retry import ShouldDelayAndRetry, exponential_backoff_interval, retry_times
from otter.util.timestamp import from_timestamp


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
            {20: [LBConfig(port=80),
                  LBConfig(port=800)],
             21: [LBConfig(port=81)]})

    def test_with_rackconnect(self):
        """
        LB config with rackconnect
        """
        self.assertEqual(
            json_to_LBConfigs([{'loadBalancerId': 20, 'port': 80},
                               {'loadBalancerId': 200, 'type': 'RackConnectV3'},
                               {'loadBalancerId': 21, 'port': 81}]),
            {20: [LBConfig(port=80)],
             21: [LBConfig(port=81)]})


class IPAddressTests(SynchronousTestCase):
    """
    Tests for utility functions that extract IP addresses from server
    dicts.
    """

    def test_private_ipv4_addresses(self):
        """
        _private_ipv4_addresses returns all private IPv4 addresses from a
        complete server body.
        """
        addresses = {
            'private': [
                {'addr': '10.0.0.1', 'version': 4},
                {'addr': '10.0.0.2', 'version': 4},
                {'addr': '::1', 'version': 6}
            ],
            'public': [
                {'addr': '50.50.50.50', 'version': 4},
                {'addr': '::::', 'version': 6}
            ]}

        result = _private_ipv4_addresses({'server': {'addresses': addresses}})
        self.assertEqual(result, ['10.0.0.1', '10.0.0.2'])
