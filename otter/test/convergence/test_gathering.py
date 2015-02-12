"""Tests for convergence gathering."""

import calendar
from functools import partial

from effect import Constant, Effect
from effect.testing import Stub

from pyrsistent import pmap

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.gathering import (
    get_all_convergence_data,
    extract_CLB_drained_at,
    get_all_server_details,
    get_clb_contents,
    get_scaling_group_servers,
    to_nova_server,
    _private_ipv4_addresses,
    _servicenet_address)
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    NovaServer,
    ServerState)
from otter.http import service_request
from otter.test.utils import (
    patch,
    resolve_effect,
    resolve_retry_stubs,
    resolve_stubs
)
from otter.util.retry import (
    ShouldDelayAndRetry, exponential_backoff_interval, retry_times)
from otter.util.timestamp import from_timestamp


def _request(requests):
    def request(service_type, method, url):
        response = requests.get((service_type, method, url))
        if response is None:
            raise KeyError("{} not in {}".format((method, url),
                                                 requests.keys()))
        return Effect(Stub(Constant(response)))
    return request


def resolve_svcreq(eff, result, service_type,
                   method, url, headers=None, data=None):
    expected_eff = service_request(
        service_type, method, url, headers=headers, data=data)
    assert eff.intent == expected_eff.intent, "%r != %r" % (
        eff.intent, expected_eff.intent)
    return resolve_effect(eff, result)


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
        fake_response = object()
        body = {'servers': self.servers}
        eff = get_all_server_details(batch_size=10)
        svcreq = resolve_retry_stubs(eff)
        result = resolve_svcreq(svcreq, (fake_response, body), *self.req)
        self.assertEqual(result, self.servers)

    def test_get_all_above_batch_size(self):
        """
        `get_all_server_details` will fetch again until batch returned has
        size < batch_size
        """
        servers = [{'id': i} for i in range(19)]
        req2 = (ServiceType.CLOUD_SERVERS, 'GET',
                'servers/detail?limit=10&marker=9')
        svcreq = resolve_retry_stubs(get_all_server_details(batch_size=10))
        fake_response = object()
        body = {'servers': servers[:10]}

        next_retry = resolve_svcreq(svcreq, (fake_response, body),
                                    *self.req)
        next_req = resolve_retry_stubs(next_retry)
        body = {'servers': servers[10:]}
        result = resolve_svcreq(next_req, (fake_response, body), *req2)
        self.assertEqual(result, servers)

    def test_retry(self):
        """The HTTP requests are retried with some appropriate policy."""
        eff = get_all_server_details(batch_size=10)
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))


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
        eff = resolve_retry_stubs(get_scaling_group_servers())
        fake_response = object()
        body = {'servers': servers}
        result = resolve_svcreq(eff, (fake_response, body), *self.req)
        self.assertEqual(result, {})

    def test_filters_no_as_metadata(self):
        """
        Does not include servers which have metadata but does not have AS info
        in it
        """
        servers = [{'id': i, 'metadata': {}} for i in range(10)]
        eff = resolve_retry_stubs(get_scaling_group_servers())
        fake_response = object()
        body = {'servers': servers}
        result = resolve_svcreq(eff, (fake_response, body), *self.req)
        self.assertEqual(result, {})

    def test_returns_as_servers(self):
        """
        Returns servers with AS metadata in it grouped by scaling group ID
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i}
             for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i}
             for i in range(5, 8)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': 10}])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        eff = resolve_retry_stubs(get_scaling_group_servers())
        fake_response = object()
        body = {'servers': servers}
        result = resolve_svcreq(eff, (fake_response, body), *self.req)
        self.assertEqual(
            result,
            {'a': as_servers[:5] + [as_servers[-1]], 'b': as_servers[5:8]})

    def test_filters_on_user_criteria(self):
        """
        Considers user provided filter if provided
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i}
             for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i}
             for i in range(5, 8)])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        eff = resolve_retry_stubs(
            get_scaling_group_servers(
                server_predicate=lambda s: s['id'] % 3 == 0))
        fake_response = object()
        body = {'servers': servers}
        result = resolve_svcreq(eff, (fake_response, body), *self.req)
        self.assertEqual(
            result,
            {'a': [as_servers[0], as_servers[3]], 'b': [as_servers[6]]})


class ExtractDrainedTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.extract_CLB_drained_at`
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
        self.assertEqual(extract_CLB_drained_at(feed),
                         calendar.timegm(from_timestamp(self.updated).utctimetuple()))

    def test_invalid_first_entry(self):
        """
        Raises error if first entry is not DRAINING entry
        """
        feed = self.feed.format("Node successfully updated with ENABLED", self.updated)
        self.assertRaises(ValueError, extract_CLB_drained_at, feed)


class GetLBContentsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.get_clb_contents`
    """

    def setUp(self):
        """
        Stub request function and mock `extract_CLB_drained_at`
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): {'loadBalancers':
                                             [{'id': 1}, {'id': 2}]},
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
            self, 'otter.convergence.gathering.extract_CLB_drained_at',
            side_effect=lambda f: self.feeds[f])

    def _resolve_request(self, eff):
        """
        Resolve a :obj:`ServiceRequest` based on ``self.reqs`` and assert
        that it's wrapped in a Retry with the expected policy.
        """
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))
        req = eff.intent.effect.intent
        body = self.reqs[(req.method, req.url, req.json_response)]
        fake_response = object()
        return resolve_effect(eff, (fake_response, body))

    def _resolve_lb(self, eff):
        """Resolve the tree of effects used to fetch LB information."""
        # first resolve the request to list LBs
        lb_nodes_fetch = self._resolve_request(eff)
        if type(lb_nodes_fetch) is not Effect:
            # If a parallel effect is *empty*, resolve_stubs will
            # simply return an empty list immediately.
            self.assertEqual(lb_nodes_fetch, [])  # sanity check
            return lb_nodes_fetch
        # which results in a parallel fetch of all nodes from all LBs
        feed_fetches = resolve_effect(
            lb_nodes_fetch,
            map(self._resolve_request, lb_nodes_fetch.intent.effects))
        # which results in a list parallel fetch of feeds for the nodes
        lbnodes = resolve_effect(
            feed_fetches,
            map(self._resolve_request, feed_fetches.intent.effects))
        # and we finally have the CLBNodes.
        return lbnodes

    def test_success(self):
        """
        Gets LB contents with drained_at correctly
        """
        eff = get_clb_contents()
        draining, enabled = CLBNodeCondition.DRAINING, CLBNodeCondition.ENABLED
        make_desc = partial(CLBDescription, port=20, type=CLBNodeType.PRIMARY)
        self.assertEqual(
            self._resolve_lb(eff),
            [CLBNode(node_id='11',
                     address='a11',
                     drained_at=1.0,
                     description=make_desc(lb_id='1',
                                           weight=2,
                                           condition=draining)),
             CLBNode(node_id='12',
                     address='a12',
                     description=make_desc(lb_id='1',
                                           weight=2,
                                           condition=enabled)),
             CLBNode(node_id='21',
                     address='a21',
                     description=make_desc(lb_id='2',
                                           weight=3,
                                           condition=enabled)),
             CLBNode(node_id='22',
                     address='a22',
                     drained_at=2.0,
                     description=make_desc(lb_id='2',
                                           weight=3,
                                           condition=draining))])

    def test_no_lb(self):
        """
        Return empty list if there are no LB
        """
        self.reqs = {('GET', 'loadbalancers', True): {'loadBalancers': []}}
        eff = get_clb_contents()
        self.assertEqual(self._resolve_lb(eff), [])

    def test_no_nodes(self):
        """
        Return empty if there are LBs but no nodes in them
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): {'loadBalancers':
                                             [{'id': 1}, {'id': 2}]},
            ('GET', 'loadbalancers/1/nodes', True): [],
            ('GET', 'loadbalancers/2/nodes', True): []
        }
        eff = get_clb_contents()
        self.assertEqual(self._resolve_lb(eff), [])

    def test_no_draining(self):
        """
        Doesnt fetch feeds if all nodes are ENABLED
        """
        self.reqs = {
            ('GET', 'loadbalancers', True): {'loadBalancers':
                                             [{'id': 1}, {'id': 2}]},
            ('GET', 'loadbalancers/1/nodes', True): [
                {'id': '11', 'port': 20, 'address': 'a11',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ],
            ('GET', 'loadbalancers/2/nodes', True): [
                {'id': '21', 'port': 20, 'address': 'a21',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ]
        }
        make_desc = partial(CLBDescription, port=20, weight=2,
                            condition=CLBNodeCondition.ENABLED,
                            type=CLBNodeType.PRIMARY)
        eff = get_clb_contents()
        self.assertEqual(
            self._resolve_lb(eff),
            [CLBNode(node_id='11', address='a11',
                     description=make_desc(lb_id='1')),
             CLBNode(node_id='21', address='a21',
                     description=make_desc(lb_id='2'))])


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
        self.servers = [{'id': 'a',
                         'status': 'ACTIVE',
                         'created': self.createds[0][0],
                         'image': {'id': 'valid_image'},
                         'flavor': {'id': 'valid_flavor'}},
                        {'id': 'b',
                         'status': 'BUILD',
                         'image': {'id': 'valid_image'},
                         'flavor': {'id': 'valid_flavor'},
                         'created': self.createds[1][0],
                         'addresses': {'private': [{'addr': u'10.0.0.1',
                                                    'version': 4}]}}]

    def test_without_address(self):
        """
        Handles server json that does not have "addresses" in it.
        """
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address=''))

    def test_without_private(self):
        """
        Creates server that does not have private/servicenet IP in it.
        """
        self.servers[0]['addresses'] = {'public': 'p'}
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address=''))

    def test_with_servicenet(self):
        """
        Create server that has servicenet IP in it.
        """
        self.assertEqual(
            to_nova_server(self.servers[1]),
            NovaServer(id='b',
                       state=ServerState.BUILD,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[1][1],
                       servicenet_address='10.0.0.1'))

    def test_without_image_id(self):
        """
        Create server that has missing image in it in various ways.
        (for the case of BFV)
        """
        for image in ({}, {'id': None}):
            self.servers[0]['image'] = image
            self.assertEqual(
                to_nova_server(self.servers[0]),
                NovaServer(id='a',
                           state=ServerState.ACTIVE,
                           image_id=None,
                           flavor_id='valid_flavor',
                           created=self.createds[0][1],
                           servicenet_address=''))
        del self.servers[0]['image']
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id=None,
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       servicenet_address=''))

    def test_with_lb_metadata(self):
        """
        Create a server that has load balancer config metadata in it.
        The only desired load balancers created are the ones with valid
        data.
        """
        self.servers[0]['metadata'] = {
            # two correct lbconfigs and one incorrect one
            'rax:autoscale:lb:12345': '[{"port":80},{"bad":"1"},{"port":90}]',
            # a dictionary instead of a list
            'rax:autoscale:lb:23456': '{"port": 80}',
            # not even valid json
            'rax:autoscale:lb:34567': 'invalid json string'
        }
        self.assertEqual(
            to_nova_server(self.servers[0]),
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='valid_image',
                       flavor_id='valid_flavor',
                       created=self.createds[0][1],
                       desired_lbs=pmap({
                           '12345': [CLBDescription(lb_id='12345', port=80),
                                     CLBDescription(lb_id='12345', port=90)]
                       }),
                       servicenet_address=''))


class IPAddressTests(SynchronousTestCase):
    """
    Tests for utility functions that extract IP addresses from server
    dicts.
    """
    def setUp(self):
        """
        Set up a bunch of addresses and a server dict.
        """
        self.addresses = {
            'private': [
                {'addr': '192.168.1.1', 'version': 4},
                {'addr': '10.0.0.1', 'version': 4},
                {'addr': '10.0.0.2', 'version': 4},
                {'addr': '::1', 'version': 6}
            ],
            'public': [
                {'addr': '50.50.50.50', 'version': 4},
                {'addr': '::::', 'version': 6}
            ]}
        self.server_dict = {'addresses': self.addresses}

    def test_private_ipv4_addresses(self):
        """
        :func:`_private_ipv4_addresses` returns all private IPv4 addresses
        from a complete server body.
        """
        result = _private_ipv4_addresses(self.server_dict)
        self.assertEqual(result, ['192.168.1.1', '10.0.0.1', '10.0.0.2'])

    def test_no_private_ip_addresses(self):
        """
        :func:`_private_ipv4_addresses` returns an empty list if the given
        server has no private IPv4 addresses.
        """
        del self.addresses["private"]
        result = _private_ipv4_addresses(self.server_dict)
        self.assertEqual(result, [])

    def test_servicenet_address(self):
        """
        :func:`_servicenet_address` returns the correct ServiceNet
        address, which is the first IPv4 address in the ``private``
        group in the 10.x.x.x range.

        It even does this when there are other addresses in the
        ``private`` group. This happens when the tenant specifies
        their own network named ``private``.
        """
        self.assertEqual(_servicenet_address(self.server_dict), "10.0.0.1")

    def test_no_servicenet_address(self):
        """
        :func:`_servicenet_address` returns :data:`None` if the server has no
        ServiceNet address.
        """
        del self.addresses["private"]
        self.assertEqual(_servicenet_address(self.server_dict), "")


class GetAllConvergenceDataTests(SynchronousTestCase):
    """Tests for :func:`get_all_convergence_data`."""

    def setUp(self):
        """Save some stuff."""
        self.servers = [
            {'id': 'a',
             'status': 'ACTIVE',
             'image': {'id': 'image'},
             'flavor': {'id': 'flavor'},
             'created': '1970-01-01T00:00:00Z',
             'addresses': {'private': [{'addr': u'10.0.0.1',
                                        'version': 4}]}},
            {'id': 'b',
             'status': 'ACTIVE',
             'image': {'id': 'image'},
             'flavor': {'id': 'flavor'},
             'created': '1970-01-01T00:00:01Z',
             'addresses': {'private': [{'addr': u'10.0.0.2',
                                        'version': 4}]}}
        ]

    def test_success(self):
        """The data is returned as a tuple of ([NovaServer], [CLBNode])."""
        lb_nodes = [CLBNode(node_id='node1', address='ip1',
                            description=CLBDescription(lb_id='lb1', port=80))]

        get_servers = lambda: Effect(Stub(Constant({'gid': self.servers})))
        get_lb = lambda: Effect(Stub(Constant(lb_nodes)))

        eff = get_all_convergence_data(
            'gid',
            get_scaling_group_servers=get_servers,
            get_clb_contents=get_lb)

        expected_servers = [
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='image',
                       flavor_id='flavor',
                       created=0,
                       servicenet_address='10.0.0.1'),
            NovaServer(id='b',
                       state=ServerState.ACTIVE,
                       image_id='image',
                       flavor_id='flavor',
                       created=1,
                       servicenet_address='10.0.0.2'),
        ]
        self.assertEqual(resolve_stubs(eff), (expected_servers, lb_nodes))

    def test_no_group_servers(self):
        """
        If there are no servers in a group, get_all_convergence_data includes
        an empty list.
        """
        get_servers = lambda: Effect(Stub(Constant({})))
        get_lb = lambda: Effect(Stub(Constant([])))

        eff = get_all_convergence_data(
            'gid',
            get_scaling_group_servers=get_servers,
            get_clb_contents=get_lb)

        self.assertEqual(resolve_stubs(eff), ([], []))
