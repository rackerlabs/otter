"""Tests for convergence gathering."""

from datetime import datetime
from functools import partial
from urllib import urlencode

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    ParallelEffects,
    TypeDispatcher,
    sync_perform)

from effect.async import perform_parallel_async
from effect.testing import EQDispatcher, EQFDispatcher, Stub

from pyrsistent import freeze

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import NoSuchEndpoint
from otter.cloud_client import service_request
from otter.constants import ServiceType
from otter.convergence.gathering import (
    UnexpectedBehaviorError,
    extract_CLB_drained_at,
    get_all_convergence_data,
    get_all_server_details,
    get_clb_contents,
    get_rcv3_contents,
    get_scaling_group_servers)
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    NovaServer,
    RCv3Description,
    RCv3Node,
    ServerState)
from otter.test.utils import (
    patch,
    resolve_effect,
    resolve_retry_stubs,
    resolve_stubs
)
from otter.util.retry import (
    ShouldDelayAndRetry, exponential_backoff_interval, retry_times)
from otter.util.timestamp import timestamp_to_epoch


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


def svc_request_args(changes_since, limit):
    """
    Return service request args with formatted changes_since argument in it
    """
    params = urlencode([('changes_since', changes_since.isoformat() + 'Z'),
                        ('limit', limit)])
    return (ServiceType.CLOUD_SERVERS, 'GET',
            'servers/detail?{}'.format(params))


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        """Save basic reused data."""
        self.servers = [{'id': i} for i in range(9)]

    def req(self, query_params=None):
        """
        Return the service request with the given query parameters
        """
        if query_params is None:
            query_params = {'limit': 10}

        url = "servers/detail?{}".format(
            "&".join(["{}={}".format(k, v) for k, v in
                      query_params.items()]))
        return (ServiceType.CLOUD_SERVERS, 'GET', url)

    def test_get_all_without_link_to_next_page(self):
        """
        `get_all_server_details` will not fetch again if first does not have
        a link to the next page (either pagination is not supported, or there
        are no more pages)
        """
        fake_response = object()
        body = {'servers': self.servers}
        eff = get_all_server_details(batch_size=10)
        svcreq = resolve_retry_stubs(eff)
        result = resolve_svcreq(svcreq, (fake_response, body), *self.req())
        self.assertEqual(result, self.servers)

    def test_get_all_ignores_non_next_links(self):
        """
        `get_all_server_details` will ignore links that do not have
        "rel" = "next".
        """
        fake_response = object()
        body = {'servers': self.servers,
                'server_links': [{
                    'href': 'https://ignoreme/path?bleh=1', 'rel': 'prev'}]}
        eff = get_all_server_details(batch_size=10)
        svcreq = resolve_retry_stubs(eff)
        result = resolve_svcreq(svcreq, (fake_response, body), *self.req())
        self.assertEqual(result, self.servers)

    def test_get_all_with_link_to_next_page(self):
        """
        `get_all_server_details` will fetch again and again until there is
        no more next page.
        """
        servers = [{'id': i} for i in range(20)]
        # first request
        svcreq = resolve_retry_stubs(get_all_server_details(batch_size=10))
        fake_response = object()
        body = {'servers': servers[:10],
                'servers_links': [{
                    'href': 'https://ignoreme/path?limit=10&marker=9',
                    'rel': 'next'}]}
        result = resolve_svcreq(svcreq, (fake_response, body), *self.req())
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?limit=10&marker=19',
                    'rel': 'next'}]}
        result = resolve_svcreq(next_req, (fake_response, body),
                                *self.req({'limit': 10, 'marker': 9}))
        self.assertIsInstance(result, Effect)

        # third request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': []}
        result = resolve_svcreq(next_req, (fake_response, body),
                                *self.req({'limit': 10, 'marker': 19}))

        self.assertEqual(result, servers)

    def test_get_all_blows_up_if_got_same_link_twice(self):
        """
        `get_all_server_details` will raise an exception if it attempts to get
        the same next page link twice in a row (not related to retries - this
        is if Nova returns the same link twice in a row)
        """
        servers = [{'id': i} for i in range(20)]
        # first request
        svcreq = resolve_retry_stubs(get_all_server_details(batch_size=10))
        fake_response = object()
        body = {'servers': servers[:10],
                'servers_links': [{
                    'href': 'https://ignoreme/path?anything=1',
                    'rel': 'next'}]}
        result = resolve_svcreq(svcreq, (fake_response, body), *self.req())
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?anything=1',
                    'rel': 'next'}]}
        self.assertRaises(UnexpectedBehaviorError,
                          resolve_svcreq, next_req, (fake_response, body),
                          *self.req({'anything': 1}))

    def test_with_changes_since(self):
        """
        `get_all_server_details` will request for servers based on
        changes_since time
        """
        fake_response = object()
        body = {'servers': self.servers}
        since = datetime(2010, 10, 10, 10, 10, 0)
        eff = get_all_server_details(changes_since=since, batch_size=10)
        svcreq = resolve_retry_stubs(eff)
        result = resolve_svcreq(
            svcreq, (fake_response, body), *svc_request_args(since, 10))
        self.assertEqual(result, self.servers)

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

    def test_with_changes_since(self):
        """
        If given, servers are fetched based on changes_since
        """
        since = datetime(2010, 10, 10, 10, 10, 0)
        eff = resolve_retry_stubs(
            get_scaling_group_servers(changes_since=since))
        fake_response = object()
        body = {'servers': []}
        result = resolve_svcreq(
            eff, (fake_response, body), *svc_request_args(since, 100))
        self.assertEqual(result, {})

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
    summary = ("Node successfully updated with address: "
               "'10.23.45.6', port: '8080', weight: '1', "
               "condition: 'DRAINING'")
    updated = '2014-10-23T18:10:48.001Z'
    feed = (
        '<feed xmlns="http://www.w3.org/2005/Atom">' +
        '<entry><summary>{}</summary><updated>{}</updated></entry>' +
        '<entry><summary>else</summary><updated>badtime</updated></entry>' +
        '</feed>')

    def test_first_entry(self):
        """
        Takes the first entry only
        """
        feed = self.feed.format(self.summary, self.updated)
        self.assertEqual(extract_CLB_drained_at(feed),
                         timestamp_to_epoch(self.updated))

    def test_invalid_first_entry(self):
        """
        Raises error if first entry is not DRAINING entry
        """
        feed = self.feed.format("Node successfully updated with ENABLED",
                                self.updated)
        self.assertRaises(ValueError, extract_CLB_drained_at, feed)


class GetCLBContentsTests(SynchronousTestCase):
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
            ('GET', 'loadbalancers/1/nodes', True): {'nodes': [
                {'id': '11', 'port': 20, 'address': 'a11',
                 'weight': 2, 'condition': 'DRAINING', 'type': 'PRIMARY'},
                {'id': '12', 'port': 20, 'address': 'a12',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}]},
            ('GET', 'loadbalancers/2/nodes', True): {'nodes': [
                {'id': '21', 'port': 20, 'address': 'a21',
                 'weight': 3, 'condition': 'ENABLED', 'type': 'PRIMARY'},
                {'id': '22', 'port': 20, 'address': 'a22',
                 'weight': 3, 'condition': 'DRAINING', 'type': 'PRIMARY'}]},
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
            ('GET', 'loadbalancers/1/nodes', True): {'nodes': []},
            ('GET', 'loadbalancers/2/nodes', True): {'nodes': []},
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
            ('GET', 'loadbalancers/1/nodes', True): {'nodes': [
                {'id': '11', 'port': 20, 'address': 'a11',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ]},
            ('GET', 'loadbalancers/2/nodes', True): {'nodes': [
                {'id': '21', 'port': 20, 'address': 'a21',
                 'weight': 2, 'condition': 'ENABLED', 'type': 'PRIMARY'}
            ]},
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


class GetRCv3ContentsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.get_rcv3_contents`
    """
    def get_dispatcher(self, service_request_mappings):
        """
        Set up an empty dictionary of intents to fake responses, and set up
        the dispatcher.
        """
        eq_dispatcher = EQDispatcher
        if callable(service_request_mappings[0][-1]):
            eq_dispatcher = EQFDispatcher

        return ComposedDispatcher([
            TypeDispatcher({
                ParallelEffects: perform_parallel_async
            }),
            eq_dispatcher(service_request_mappings)
        ])

    def test_returns_flat_list_of_rcv3nodes(self):
        """
        All the nodes returned are in a flat list.
        """
        dispatcher = self.get_dispatcher([
            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools').intent,
             (None, [{'id': str(i)} for i in range(2)])),

            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools/0/nodes').intent,
             (None,
              [{'id': "0node{0}".format(i),
                'cloud_server': {'id': '0server{0}'.format(i)}}
               for i in range(2)])),

            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools/1/nodes').intent,
             (None,
              [{'id': "1node{0}".format(i),
                'cloud_server': {'id': '1server{0}'.format(i)}}
               for i in range(2)])),
        ])

        self.assertEqual(
            sorted(sync_perform(dispatcher, get_rcv3_contents())),
            sorted(
                [RCv3Node(node_id='0node0', cloud_server_id='0server0',
                          description=RCv3Description(lb_id='0')),
                 RCv3Node(node_id='0node1', cloud_server_id='0server1',
                          description=RCv3Description(lb_id='0')),
                 RCv3Node(node_id='1node0', cloud_server_id='1server0',
                          description=RCv3Description(lb_id='1')),
                 RCv3Node(node_id='1node1', cloud_server_id='1server1',
                          description=RCv3Description(lb_id='1'))]))

    def test_no_lb_pools_returns_no_nodes(self):
        """
        If there are no load balancer pools, there are no nodes.
        """
        dispatcher = self.get_dispatcher([(
            service_request(ServiceType.RACKCONNECT_V3, 'GET',
                            'load_balancer_pools').intent,
            (None, [])
        )])
        self.assertEqual(
            sync_perform(dispatcher, get_rcv3_contents()), [])

    def test_no_nodes_on_lbs_no_nodes(self):
        """
        If there are no nodes on each of the load balancer pools, there are no
        nodes returned overall.
        """
        dispatcher = self.get_dispatcher([
            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools').intent,
             (None, [{'id': str(i)} for i in range(2)])),

            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools/0/nodes').intent,
             (None, [])),

            (service_request(ServiceType.RACKCONNECT_V3, 'GET',
                             'load_balancer_pools/1/nodes').intent,
             (None, []))
        ])

        self.assertEqual(
            sync_perform(dispatcher, get_rcv3_contents()), [])

    def test_rackconnect_not_supported_on_tenant(self):
        """
        If RackConnectV3 is not supported, return no nodes.
        """
        def no_endpoint(intent):
            raise NoSuchEndpoint(service_name='RackConnect', region='DFW')

        dispatcher = self.get_dispatcher([(
            service_request(ServiceType.RACKCONNECT_V3, 'GET',
                            'load_balancer_pools').intent,
            no_endpoint
        )])
        self.assertEqual(
            sync_perform(dispatcher, get_rcv3_contents()), [])


def _constant_as_eff(constant):
    return lambda: Effect(Stub(Constant(constant)))


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
                                        'version': 4}]},
             'links': [{'href': 'link1', 'rel': 'self'}]},
            {'id': 'b',
             'status': 'ACTIVE',
             'image': {'id': 'image'},
             'flavor': {'id': 'flavor'},
             'created': '1970-01-01T00:00:01Z',
             'addresses': {'private': [{'addr': u'10.0.0.2',
                                        'version': 4}]},
             'links': [{'href': 'link2', 'rel': 'self'}]}
        ]

    def test_success(self):
        """
        The data is returned as a tuple of ([NovaServer], [CLBNode/RCv3Node]).
        """
        clb_nodes = [CLBNode(node_id='node1', address='ip1',
                             description=CLBDescription(lb_id='lb1', port=80))]
        rcv3_nodes = [RCv3Node(node_id='node2', cloud_server_id='a',
                               description=RCv3Description(lb_id='lb2'))]

        eff = get_all_convergence_data(
            'gid',
            get_scaling_group_servers=_constant_as_eff({'gid': self.servers}),
            get_clb_contents=_constant_as_eff(clb_nodes),
            get_rcv3_contents=_constant_as_eff(rcv3_nodes))

        expected_servers = [
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       image_id='image',
                       flavor_id='flavor',
                       created=0,
                       servicenet_address='10.0.0.1',
                       links=freeze([{'href': 'link1', 'rel': 'self'}])),
            NovaServer(id='b',
                       state=ServerState.ACTIVE,
                       image_id='image',
                       flavor_id='flavor',
                       created=1,
                       servicenet_address='10.0.0.2',
                       links=freeze([{'href': 'link2', 'rel': 'self'}]))
        ]
        self.assertEqual(resolve_stubs(eff),
                         (expected_servers, clb_nodes + rcv3_nodes))

    def test_no_group_servers(self):
        """
        If there are no servers in a group, get_all_convergence_data includes
        an empty list.
        """
        eff = get_all_convergence_data(
            'gid',
            get_scaling_group_servers=_constant_as_eff({}),
            get_clb_contents=_constant_as_eff([]),
            get_rcv3_contents=_constant_as_eff([]))

        self.assertEqual(resolve_stubs(eff), ([], []))
