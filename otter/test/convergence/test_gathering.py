"""Tests for convergence gathering."""

from copy import deepcopy
from datetime import datetime
from functools import partial

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    ParallelEffects,
    TypeDispatcher,
    sync_perform)

from effect.async import perform_parallel_async
from effect.testing import (
    EQDispatcher, EQFDispatcher, Stub)

import mock

from pyrsistent import freeze

from toolz.curried import map
from toolz.functoolz import compose

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import NoSuchEndpoint
from otter.cloud_client import (
    CLBNotFoundError,
    NovaComputeFaultError,
    service_request
)
from otter.constants import ServiceType
from otter.convergence.gathering import (
    extract_CLB_drained_at,
    get_all_convergence_data,
    get_all_scaling_group_servers,
    get_all_server_details,
    get_clb_contents,
    get_rcv3_contents,
    get_scaling_group_servers,
    mark_deleted_servers)
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    RCv3Description,
    RCv3Node,
    ServerState)
from otter.test.utils import (
    EffectServersCache,
    StubResponse,
    intent_func,
    nested_parallel,
    nested_sequence,
    patch,
    perform_sequence,
    resolve_effect,
    resolve_stubs,
    server
)
from otter.util.fp import assoc_obj
from otter.util.retry import (
    Retry, ShouldDelayAndRetry, exponential_backoff_interval, retry_times)
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
                   method, url, params=None, headers=None, data=None):
    expected_eff = service_request(
        service_type, method, url, params=params, headers=headers, data=data)
    assert eff.intent == expected_eff.intent, "%r != %r" % (
        eff.intent, expected_eff.intent)
    return resolve_effect(eff, result)


def svc_request_args(**params):
    """
    Return service request args with formatted changes_since argument in it
    """
    changes_since = params.pop('changes_since', None)
    if changes_since is not None:
        params['changes-since'] = changes_since.isoformat() + 'Z'
    return {
        'service_type': ServiceType.CLOUD_SERVERS,
        'method': 'GET',
        'params': {k: [str(v)] for k, v in params.iteritems()},
        'url': 'servers/detail'}


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        """Save basic reused data."""
        self.servers = [{'id': i} for i in range(9)]

    def test_get_all_without_link_to_next_page(self):
        """
        `get_all_server_details` will not fetch again if first does not have
        a link to the next page (either pagination is not supported, or there
        are no more pages)
        """
        fake_response = object()
        body = {'servers': self.servers}
        svcreq = get_all_server_details(batch_size=10)
        result = resolve_svcreq(
            svcreq, (fake_response, body), **svc_request_args(limit=10))
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
        svcreq = get_all_server_details(batch_size=10)
        result = resolve_svcreq(
            svcreq, (fake_response, body), **svc_request_args(limit=10))
        self.assertEqual(result, self.servers)

    def test_get_all_with_link_to_next_page(self):
        """
        `get_all_server_details` will fetch again and again until there is
        no more next page.
        """
        servers = [{'id': i} for i in range(20)]
        # first request
        svcreq = get_all_server_details(batch_size=10)
        fake_response = object()
        body = {'servers': servers[:10],
                'servers_links': [{
                    'href': 'https://ignoreme/path?limit=10&marker=9',
                    'rel': 'next'}]}
        result = resolve_svcreq(
            svcreq, (fake_response, body), **svc_request_args(limit=10))
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = result
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?limit=10&marker=19',
                    'rel': 'next'}]}
        result = resolve_svcreq(
            next_req, (fake_response, body),
            **svc_request_args(limit=10, marker=9))
        self.assertIsInstance(result, Effect)

        # third request, because previous had a next link
        next_req = result
        body = {'servers': []}
        result = resolve_svcreq(next_req, (fake_response, body),
                                **svc_request_args(limit=10, marker=19))

        self.assertEqual(result, servers)

    def test_get_all_blows_up_if_got_same_link_twice(self):
        """
        `get_all_server_details` will raise an exception if it attempts to get
        the same next page link twice in a row (not related to retries - this
        is if Nova returns the same link twice in a row)
        """
        servers = [{'id': i} for i in range(20)]
        # first request
        svcreq = get_all_server_details(batch_size=10)
        fake_response = object()
        body = {'servers': servers[:10],
                'servers_links': [{
                    'href': 'https://ignoreme/path?anything=1',
                    'rel': 'next'}]}
        result = resolve_svcreq(svcreq, (fake_response, body),
                                **svc_request_args(limit=10))
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = result
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?anything=1',
                    'rel': 'next'}]}
        self.assertRaises(NovaComputeFaultError,
                          resolve_svcreq, next_req, (fake_response, body),
                          **svc_request_args(anything=1))

    def test_with_changes_since(self):
        """
        `get_all_server_details` will request for servers based on
        changes_since time
        """
        fake_response = object()
        body = {'servers': self.servers}
        since = datetime(2010, 10, 10, 10, 10, 0)
        svcreq = get_all_server_details(changes_since=since, batch_size=10)
        result = resolve_svcreq(
            svcreq, (fake_response, body),
            **svc_request_args(changes_since=since, limit=10))
        self.assertEqual(result, self.servers)


class GetAllScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_scaling_group_servers`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail', {'limit': ['100']})

    def test_with_changes_since(self):
        """
        If given, servers are fetched based on changes_since
        """
        since = datetime(2010, 10, 10, 10, 10, 0)
        eff = get_all_scaling_group_servers(changes_since=since)
        fake_response = object()
        body = {'servers': []}
        result = resolve_svcreq(
            eff, (fake_response, body),
            **svc_request_args(changes_since=since, limit=100))
        self.assertEqual(result, {})

    def test_filters_no_metadata(self):
        """
        Servers without metadata are not included in the result.
        """
        servers = [{'id': i} for i in range(10)]
        eff = get_all_scaling_group_servers()
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
        eff = get_all_scaling_group_servers()
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
        eff = get_all_scaling_group_servers()
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
        eff = get_all_scaling_group_servers(
            server_predicate=lambda s: s['id'] % 3 == 0)
        fake_response = object()
        body = {'servers': servers}
        result = resolve_svcreq(eff, (fake_response, body), *self.req)
        self.assertEqual(
            result,
            {'a': [as_servers[0], as_servers[3]], 'b': [as_servers[6]]})


class GetScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_scaling_group_servers`
    """

    def setUp(self):
        self.now = datetime(2010, 5, 31)
        self.freeze = compose(set, map(freeze))

    def _invoke(self):
        return get_scaling_group_servers(
            'tid', 'gid', self.now, cache_class=EffectServersCache,
            all_as_servers=intent_func("all-as"),
            all_servers=intent_func("alls"))

    def _test_no_cache(self, empty):
        current = [] if empty else [{'id': 'a', 'a': 'b'},
                                    {'id': 'b', 'b': 'c'}]
        sequence = [
            (("cachegstidgid", False), lambda i: (object(), None)),
            (("all-as",), lambda i: {} if empty else {"gid": current})]
        self.assertEqual(perform_sequence(sequence, self._invoke()), current)

    def test_no_cache(self):
        """
        If cache is empty then current list of servers are returned
        """
        self._test_no_cache(False)
        self._test_no_cache(True)

    def test_from_cache(self):
        """
        If cache is there then servers returned are updated with servers
        not found in current list marked as deleted
        """
        asmetakey = "rax:autoscale:group:id"
        cache = [
            {'id': 'a', 'metadata': {asmetakey: "gid"}},
            {'id': 'b', 'metadata': {asmetakey: "gid"}},
            {'id': 'd', 'metadata': {asmetakey: "gid"}}]
        current = [
            {'id': 'a', 'b': 'c', 'metadata': {asmetakey: "gid"}},
            {'id': 'd', 'metadata': {"changed": "yes"}}]
        last_update = datetime(2010, 5, 20)
        sequence = [
            (("cachegstidgid", False), lambda i: (cache, last_update)),
            (("alls",), lambda i: current)]
        exp_cache_server = deepcopy(cache[1])
        exp_cache_server["status"] = "DELETED"
        self.assertEqual(
            self.freeze(perform_sequence(sequence, self._invoke())),
            self.freeze([exp_cache_server, current[0]]))

    def test_mark_deleted_servers_precedence(self):
        """
        In :func:`mark_deleted_servers`, if old list has common servers with
        new list, the new one takes precedence
        """
        old = [{'id': 'a', 'a': 1}, {'id': 'b', 'b': 2}]
        new = [{'id': 'd', 'd': 3}, {'id': 'b', 'b': 4}]
        old_server = deepcopy(old[0])
        old_server["status"] = "DELETED"
        self.assertEqual(
            self.freeze(mark_deleted_servers(old, new)),
            self.freeze([old_server] + new))

    def test_mark_deleted_servers_no_old(self):
        """
        If old list does not have any servers then it just returns new list
        """
        new = [{'id': 'd', 'd': 3}, {'id': 'b', 'b': 4}]
        self.assertEqual(
            self.freeze(mark_deleted_servers([], new)), self.freeze(new))

    def test_updated_deleted_servers_no_new(self):
        """
        If new list does not have any servers then old list is updated as
        DELETED and returned
        """
        old = [{'id': 'd', 'd': 3}, {'id': 'b', 'b': 4}]
        exp_old = deepcopy(old)
        exp_old[0]["status"] = "DELETED"
        exp_old[1]["status"] = "DELETED"
        self.assertEqual(
            self.freeze(mark_deleted_servers(old, [])),
            self.freeze(exp_old))


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


def lb_req(url, json_response, response):
    """
    Return a SequenceDispatcher two-tuple that matches a service request to a
    particular load balancer endpoint (using GET), and returns the given
    ``response`` as the content in an HTTP 200 ``StubResponse``.
    """
    if isinstance(response, Exception):
        def handler(i): raise response
    else:
        def handler(i): return (StubResponse(200, {}), response)
    return (
        Retry(
            effect=mock.ANY,
            should_retry=ShouldDelayAndRetry(
                can_retry=retry_times(5),
                next_interval=exponential_backoff_interval(2))
        ),
        nested_sequence([
            (service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'GET', url, json_response=json_response).intent,
             handler)
        ])
    )


def nodes_req(lb_id, nodes):
    return lb_req('loadbalancers/{}/nodes'.format(lb_id),
                  True, {'nodes': nodes})


def node_feed_req(lb_id, node_id, response):
    return lb_req(
        'loadbalancers/{}/nodes/{}.atom'.format(lb_id, node_id),
        False, response)


def node(id, address, port=20, weight=2, condition='ENABLED',
         type='PRIMARY'):
    d = {'id': id, 'port': port, 'address': address, 'condition': condition,
         'type': type}
    if weight is not None:
        d['weight'] = weight
    return d


class GetCLBContentsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.get_clb_contents`
    """

    def setUp(self):
        """mock `extract_CLB_drained_at`"""
        self.feeds = {'11feed': 1.0, '22feed': 2.0}
        self.mock_eda = patch(
            self, 'otter.convergence.gathering.extract_CLB_drained_at',
            side_effect=lambda f: self.feeds[f])

    def test_success(self):
        """
        Gets LB contents with drained_at correctly
        """
        node11 = node('11', 'a11', condition='DRAINING')
        node12 = node('12', 'a12')
        node21 = node('21', 'a21', weight=3)
        node22 = node('22', 'a22', weight=None, condition='DRAINING')
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([nodes_req(1, [node11, node12]),
                             nodes_req(2, [node21, node22])]),
            nested_parallel([node_feed_req(1, '11', '11feed'),
                             node_feed_req(2, '22', '22feed')]),
        ]
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [assoc_obj(CLBNode.from_node_json(1, node11), drained_at=1.0),
             CLBNode.from_node_json(1, node12),
             CLBNode.from_node_json(2, node21),
             assoc_obj(CLBNode.from_node_json(2, node22), drained_at=2.0)])

    def test_no_lb(self):
        """
        Return empty list if there are no LB
        """
        seq = [
            lb_req('loadbalancers', True, {'loadBalancers': []}),
            nested_parallel([]),  # No LBs to fetch
            nested_parallel([]),  # No nodes to fetch
        ]
        eff = get_clb_contents()
        self.assertEqual(perform_sequence(seq, eff), [])

    def test_no_nodes(self):
        """
        Return empty if there are LBs but no nodes in them
        """
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([nodes_req(1, []), nodes_req(2, [])]),
            nested_parallel([]),  # No nodes to fetch
        ]
        self.assertEqual(perform_sequence(seq, get_clb_contents()), [])

    def test_no_draining(self):
        """
        Doesnt fetch feeds if all nodes are ENABLED
        """
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([nodes_req(1, [node('11', 'a11')]),
                             nodes_req(2, [node('21', 'a21')])]),
            nested_parallel([])  # No nodes to fetch
        ]
        make_desc = partial(CLBDescription, port=20, weight=2,
                            condition=CLBNodeCondition.ENABLED,
                            type=CLBNodeType.PRIMARY)
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [CLBNode(node_id='11', address='a11',
                     description=make_desc(lb_id='1')),
             CLBNode(node_id='21', address='a21',
                     description=make_desc(lb_id='2'))])

    def test_lb_disappeared_during_node_fetch(self):
        """
        If a load balancer gets deleted while fetching nodes, no nodes will be
        returned for it.
        """
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                nodes_req(1, [node('11', 'a11')]),
                lb_req('loadbalancers/2/nodes', True,
                       CLBNotFoundError(lb_id=u'2')),
            ]),
            nested_parallel([])  # No nodes to fetch
        ]
        make_desc = partial(CLBDescription, port=20, weight=2,
                            condition=CLBNodeCondition.ENABLED,
                            type=CLBNodeType.PRIMARY)
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [CLBNode(node_id='11', address='a11',
                     description=make_desc(lb_id='1'))])

    def test_lb_disappeared_during_feed_fetch(self):
        """
        If a load balancer gets deleted while fetching feeds, no nodes will be
        returned for it.
        """
        node21 = node('21', 'a21', condition='DRAINING', weight=None)
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                nodes_req(1, [node('11', 'a11', condition='DRAINING'),
                              node('12', 'a12')]),
                nodes_req(2, [node21])
            ]),
            nested_parallel([
                node_feed_req(1, '11', CLBNotFoundError(lb_id=u'1')),
                node_feed_req(2, '21', '22feed')]),
        ]
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [assoc_obj(CLBNode.from_node_json(2, node21), drained_at=2.0)])


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


def _constant_as_eff(args, retval):
    return lambda *a: Effect(Stub(Constant(retval))) if a == args else (1 / 0)


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
        self.now = datetime(2010, 10, 20, 03, 30, 00)

    def test_success(self):
        """
        The data is returned as a tuple of ([NovaServer], [CLBNode/RCv3Node]).
        """
        clb_nodes = [CLBNode(node_id='node1', address='ip1',
                             description=CLBDescription(lb_id='lb1', port=80))]
        rcv3_nodes = [RCv3Node(node_id='node2', cloud_server_id='a',
                               description=RCv3Description(lb_id='lb2'))]

        eff = get_all_convergence_data(
            'tid',
            'gid',
            self.now,
            get_scaling_group_servers=_constant_as_eff(
                ('tid', 'gid', self.now), self.servers),
            get_clb_contents=_constant_as_eff((), clb_nodes),
            get_rcv3_contents=_constant_as_eff((), rcv3_nodes))

        expected_servers = [
            server('a', ServerState.ACTIVE, servicenet_address='10.0.0.1',
                   links=freeze([{'href': 'link1', 'rel': 'self'}]),
                   json=freeze(self.servers[0])),
            server('b', ServerState.ACTIVE, created=1,
                   servicenet_address='10.0.0.2',
                   links=freeze([{'href': 'link2', 'rel': 'self'}]),
                   json=freeze(self.servers[1]))
        ]
        self.assertEqual(resolve_stubs(eff),
                         (expected_servers, clb_nodes + rcv3_nodes))

    def test_no_group_servers(self):
        """
        If there are no servers in a group, get_all_convergence_data includes
        an empty list.
        """
        eff = get_all_convergence_data(
            'tid',
            'gid',
            self.now,
            get_scaling_group_servers=_constant_as_eff(
                ('tid', 'gid', self.now), []),
            get_clb_contents=_constant_as_eff((), []),
            get_rcv3_contents=_constant_as_eff((), []))

        self.assertEqual(resolve_stubs(eff), ([], []))
