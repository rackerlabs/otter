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
    EQDispatcher, EQFDispatcher, Stub, parallel_sequence, perform_sequence)

import mock

from pyrsistent import freeze

from toolz.curried import map
from toolz.functoolz import compose

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import NoSuchEndpoint
from otter.cloud_client import (
    CLBNotFoundError,
    service_request
)
from otter.constants import ServiceType
from otter.convergence.gathering import (
    extract_clb_drained_at,
    get_all_launch_server_data,
    get_all_launch_stack_data,
    get_all_scaling_group_servers,
    get_all_server_details,
    get_all_stacks,
    get_clb_contents,
    get_rcv3_contents,
    get_scaling_group_servers,
    get_scaling_group_stacks,
    mark_deleted_servers)
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    RCv3Description,
    RCv3Node,
    ServerState)
from otter.indexer import atom
from otter.log.intents import Log
from otter.test.utils import (
    EffectServersCache,
    StubResponse,
    intent_func,
    nested_sequence,
    patch,
    resolve_stubs,
    server,
    stack
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
    Tests for :func:`get_all_server_details`.  The service request is
    constructed and handled by `cloud_client`.  :func:`get_all_server_details`
    just handles constructing the parameters.
    """
    def test_default_arguments(self):
        """
        :func:`get_all_server_details` called with arguments will use a default
        batch size.
        """
        self.assertEqual(get_all_server_details().intent,
                         service_request(**svc_request_args(limit=100)).intent)

    def test_respects_batch_size_and_changes_since(self):
        """
        :func:`get_all_server_details` will respect the changes since and
        batch size arguments, and convert changes-since to an ISO8601 zulu
        format.
        """
        since = datetime(2010, 10, 10, 10, 10, 0)
        self.assertEqual(
            get_all_server_details(batch_size=10, changes_since=since).intent,
            service_request(
                **svc_request_args(limit=10, changes_since=since)).intent
        )


class GetAllScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_scaling_group_servers`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail', None, None, {'limit': ['100']})

    def test_with_changes_since(self):
        """
        If given, servers are fetched based on changes_since
        """
        since = datetime(2010, 10, 10, 10, 10, 0)
        eff = get_all_scaling_group_servers(changes_since=since)
        body = {'servers': []}

        sequence = [
            (service_request(
                **svc_request_args(changes_since=since, limit=100)).intent,
             lambda i: (StubResponse(200, None), body)),
            (Log(mock.ANY, mock.ANY), lambda i: None)
        ]
        result = perform_sequence(sequence, eff)
        self.assertEqual(result, {})

    def test_filters_no_metadata(self):
        """
        Servers without metadata are not included in the result.
        """
        servers = [{'id': i} for i in range(10)]
        eff = get_all_scaling_group_servers()
        body = {'servers': servers}
        sequence = [
            (service_request(*self.req).intent,
             lambda i: (StubResponse(200, None), body)),
            (Log(mock.ANY, mock.ANY), lambda i: None)
        ]
        result = perform_sequence(sequence, eff)
        self.assertEqual(result, {})

    def test_filters_no_as_metadata(self):
        """
        Does not include servers which have metadata but does not have AS info
        in it
        """
        servers = [{'id': i, 'metadata': {}} for i in range(10)]
        eff = get_all_scaling_group_servers()
        body = {'servers': servers}
        sequence = [
            (service_request(*self.req).intent,
             lambda i: (StubResponse(200, None), body)),
            (Log(mock.ANY, mock.ANY), lambda i: None)
        ]
        result = perform_sequence(sequence, eff)
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
        body = {'servers': servers}
        sequence = [
            (service_request(*self.req).intent,
             lambda i: (StubResponse(200, None), body)),
            (Log(mock.ANY, mock.ANY), lambda i: None)
        ]
        result = perform_sequence(sequence, eff)
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
        body = {'servers': servers}
        sequence = [
            (service_request(*self.req).intent,
             lambda i: (StubResponse(200, None), body)),
            (Log(mock.ANY, mock.ANY), lambda i: None)
        ]
        result = perform_sequence(sequence, eff)
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
            {'id': 'a', 'metadata': {asmetakey: "gid"}},  # gets updated
            {'id': 'b', 'metadata': {asmetakey: "gid"}},  # deleted
            {'id': 'd', 'metadata': {asmetakey: "gid"}},  # meta removed
            {'id': 'c', 'metadata': {asmetakey: "gid"}}]  # same
        current = [
            {'id': 'a', 'b': 'c', 'metadata': {asmetakey: "gid"}},
            {'id': 'z', 'z': 'w', 'metadata': {asmetakey: "gid"}},  # new
            {'id': 'd', 'metadata': {"changed": "yes"}},
            {'id': 'c', 'metadata': {asmetakey: "gid"}}]
        last_update = datetime(2010, 5, 20)
        sequence = [
            (("cachegstidgid", False), lambda i: (cache, last_update)),
            (("alls",), lambda i: current)]
        del_cache_server = deepcopy(cache[1])
        del_cache_server["status"] = "DELETED"
        self.assertEqual(
            self.freeze(perform_sequence(sequence, self._invoke())),
            self.freeze([del_cache_server, cache[-1]] + current[0:2]))

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
    Tests for :func:`otter.convergence.extract_clb_drained_at`
    """
    updated_summary = ("Node successfully updated with address: "
                       "'10.23.45.6', port: '8080', weight: '1', "
                       "condition: 'DRAINING'")
    created_summary = ("Node successfully created with address: "
                       "'10.23.45.6', port: '8080', condition: 'DRAINING', "
                       "weight: '1'")
    updated1 = '2014-10-23T18:10:48.001Z'
    updated2 = '2015-09-23T08:00:40Z'
    entry = '<entry><summary>{}</summary><updated>{}</updated></entry>'
    feed = '<feed xmlns="http://www.w3.org/2005/Atom">{}</feed>'

    def parsed_feed(self, *entries):
        entries = ''.join(self.entry.format(*e) for e in entries)
        return atom.entries(atom.parse(self.feed.format(entries)))

    def test_updated(self):
        """
        Returns time matched from first "Node updated" entry found in feeds
        """
        feed = self.parsed_feed(
            ("summary", "2000-10-01Z"),
            (self.updated_summary, self.updated1),
            ("don't care", self.updated2))
        self.assertEqual(
            extract_clb_drained_at(feed), timestamp_to_epoch(self.updated1))

    def test_created(self):
        """
        Returns time matched from first "Node created" entry found in feeds
        """
        feed = self.parsed_feed(
            ("summary", "2000-10-01Z"), (self.created_summary, self.updated2))
        self.assertEqual(
            extract_clb_drained_at(feed), timestamp_to_epoch(self.updated2))

    def test_no_match(self):
        """
        Returns None when no entry matches
        """
        feed = self.parsed_feed(
            ("summary", self.updated1), ("don't care", self.updated2))
        self.assertIsNone(extract_clb_drained_at(feed))

    def test_empty(self):
        """
        Returns None when there are no entries in the feed
        """
        self.assertIsNone(extract_clb_drained_at([]))


def lb_req(url, json_response, response):
    """
    Return a SequenceDispatcher two-tuple that matches a service request to a
    particular load balancer endpoint (using GET), and returns the given
    ``response`` as the content in an HTTP 200 ``StubResponse``.
    """
    if isinstance(response, Exception):
        def handler(i): raise response
        log_seq = []
    else:
        def handler(i): return (StubResponse(200, {}), response)
        log_seq = [(Log(mock.ANY, mock.ANY), lambda i: None)]
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
        ] + log_seq)
    )


def nodes_req(lb_id, nodes):
    return lb_req('loadbalancers/{}/nodes'.format(lb_id),
                  True, {'nodes': nodes})


def lb_hm_req(lb_id, health_mon):
    return lb_req('loadbalancers/{}/healthmonitor'.format(lb_id), True,
                  {'healthMonitor': health_mon})


def node_feed_req(lb_id, node_id, response):
    """
    Return (intent, performer) sequence for getting clb node's feed that
    wrapped with retry intent.

    :param lb_id: Lodbalancer ID
    :param node_id: LB node ID
    :param response: The response returned when getting CLB node feed. It is
        either string containing feed or Exception object that will be raised
        when getting the feed

    :return: (intent, performer) tuple
    """
    if isinstance(response, Exception):
        def handler(i): raise response
    else:
        def handler(i): return response
    return (
        Retry(
            effect=mock.ANY,
            should_retry=ShouldDelayAndRetry(
                can_retry=retry_times(5),
                next_interval=exponential_backoff_interval(2))
        ),
        nested_sequence([(("gcnf", lb_id, node_id), handler)])
    )


def node(id, address, port=20, weight=2, condition='ENABLED',
         type='PRIMARY'):
    d = {'id': id, 'port': port, 'address': address, 'condition': condition,
         'type': type, "status": "ONLINE"}
    if weight is not None:
        d['weight'] = weight
    return d


class GetCLBContentsTests(SynchronousTestCase):
    """
    Tests for :func:`otter.convergence.get_clb_contents`
    """

    def setUp(self):
        """mock `extract_clb_drained_at`"""
        self.feeds = {'11feed': 1.0, '22feed': 2.0}
        self.mock_eda = patch(
            self, 'otter.convergence.gathering.extract_clb_drained_at',
            side_effect=lambda f: self.feeds[f])
        patch(self, "otter.convergence.gathering.get_clb_node_feed",
              side_effect=intent_func("gcnf"))

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
            parallel_sequence([[nodes_req(1, [node11, node12])],
                               [nodes_req(2, [node21, node22])],
                               [lb_hm_req(1, {"type": "CONNECT"})],
                               [lb_hm_req(2, {})]]),
            parallel_sequence([[node_feed_req('1', '11', '11feed')],
                               [node_feed_req('2', '22', '22feed')]]),
        ]
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [assoc_obj(CLBNode.from_node_json(1, node11, True),
                       drained_at=1.0),
             CLBNode.from_node_json(1, node12, True),
             CLBNode.from_node_json(2, node21, False),
             assoc_obj(CLBNode.from_node_json(2, node22, False),
                       drained_at=2.0)])

    def test_no_lb(self):
        """
        Return empty list if there are no LB
        """
        seq = [
            lb_req('loadbalancers', True, {'loadBalancers': []}),
            parallel_sequence([]),  # No LBs to fetch
            parallel_sequence([]),  # No nodes to fetch
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
            parallel_sequence([
                [nodes_req(1, [])], [nodes_req(2, [])],
                [lb_hm_req(1, {})], [lb_hm_req(2, {})]
            ]),
            parallel_sequence([]),  # No nodes to fetch
        ]
        self.assertEqual(perform_sequence(seq, get_clb_contents()), [])

    def test_no_draining(self):
        """
        Doesnt fetch feeds if all nodes are ENABLED
        """
        seq = [
            lb_req('loadbalancers', True,
                   {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            parallel_sequence([[nodes_req(1, [node('11', 'a11')])],
                               [nodes_req(2, [node('21', 'a21')])],
                               [lb_hm_req(1, {})],
                               [lb_hm_req(2, {})]]),
            parallel_sequence([])  # No nodes to fetch
        ]
        make_desc = partial(CLBDescription, port=20, weight=2,
                            condition=CLBNodeCondition.ENABLED,
                            type=CLBNodeType.PRIMARY, health_monitor=False)
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
            parallel_sequence([
                [nodes_req(1, [node('11', 'a11')])],
                [lb_req('loadbalancers/2/nodes', True,
                        CLBNotFoundError(lb_id=u'2'))],
                [lb_hm_req(1, {"type": "CONNECT"})],
                [lb_req('loadbalancers/2/healthmonitor', True,
                        CLBNotFoundError(lb_id=u'2'))]
            ]),
            parallel_sequence([])  # No node feeds to fetch
        ]
        make_desc = partial(CLBDescription, port=20, weight=2,
                            condition=CLBNodeCondition.ENABLED,
                            type=CLBNodeType.PRIMARY, health_monitor=True)
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
            parallel_sequence([
                [nodes_req(1, [node('11', 'a11', condition='DRAINING'),
                               node('12', 'a12')])],
                [nodes_req(2, [node21])],
                [lb_hm_req(1, {"type": "CONNECT"})],
                [lb_hm_req(2, {"type": "CONNECT"})]
            ]),
            parallel_sequence([
                [node_feed_req('1', '11', CLBNotFoundError(lb_id=u'1'))],
                [node_feed_req('2', '21', '22feed')]]),
        ]
        eff = get_clb_contents()
        self.assertEqual(
            perform_sequence(seq, eff),
            [assoc_obj(CLBNode.from_node_json(2, node21, True),
                       drained_at=2.0)])


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


class GetAllLaunchServerDataTests(SynchronousTestCase):
    """Tests for :func:`get_all_launch_server_data`."""

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

        eff = get_all_launch_server_data(
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
                         {'servers': expected_servers,
                          'lb_nodes': clb_nodes + rcv3_nodes})

    def test_no_group_servers(self):
        """
        If there are no servers in a group, get_all_launch_server_data includes
        an empty list.
        """
        eff = get_all_launch_server_data(
            'tid',
            'gid',
            self.now,
            get_scaling_group_servers=_constant_as_eff(
                ('tid', 'gid', self.now), []),
            get_clb_contents=_constant_as_eff((), []),
            get_rcv3_contents=_constant_as_eff((), []))

        self.assertEqual(resolve_stubs(eff), {'servers': [], 'lb_nodes': []})


class GetAllStacksTests(SynchronousTestCase):
    """Tests for :func:`get_all_stacks`."""

    def test_default(self):
        """Passing no arguments causes all stacks to be requested."""
        svc_intent = service_request(ServiceType.CLOUD_ORCHESTRATION, 'GET',
                                     'stacks', reauth_codes=(401,),
                                     params={}).intent
        self.assertEqual(get_all_stacks().intent, svc_intent)

    def test_stack_tag(self):
        """The query parameters include `tags` when `stack_tag` is passed."""
        tag = 'footag'
        svc_intent = service_request(ServiceType.CLOUD_ORCHESTRATION, 'GET',
                                     'stacks', reauth_codes=(401,),
                                     params={'tags': tag}).intent
        self.assertEqual(get_all_stacks(stack_tag=tag).intent, svc_intent)


class GetScalingGroupStacksTests(SynchronousTestCase):
    """Tests for :func:`get_scaling_group_stacks`."""

    def test_normal_use(self):
        """
        The correct stack tag should be included in when retrieving stacks.
        """
        def fake_get_all_stacks(stack_tag):
            return Effect(('all-stacks', stack_tag))

        seq = [(('all-stacks', 'autoscale_gid'), lambda _: [])]
        eff = get_scaling_group_stacks('gid',
                                       get_all_stacks=fake_get_all_stacks)

        result = perform_sequence(seq, eff)
        self.assertEqual(result, [])


class GetAllLaunchStackDataTests(SynchronousTestCase):
    """Tests for :func:`get_all_launch_stack_data`."""

    def setUp(self):
        """Save reused data."""
        self.stacks = [
            {'id': 'a', 'stack_name': 'aa', 'stack_status': 'CREATE_COMPLETE'},
            {'id': 'b', 'stack_name': 'bb', 'stack_status': 'CREATE_COMPLETE'}
        ]
        self.now = datetime(2010, 10, 20, 03, 30, 00)

    def test_success(self):
        """HeatStack instances should be returned from JSON."""
        expected_stacks = [
            stack(id='a', name='aa', action='CREATE', status='COMPLETE'),
            stack(id='b', name='bb', action='CREATE', status='COMPLETE')
        ]
        eff = get_all_launch_stack_data(
            'tid',
            'gid',
            self.now,
            get_scaling_group_stacks=_constant_as_eff(('gid',), self.stacks))

        self.assertEqual(resolve_stubs(eff), {'stacks': expected_stacks})

    def test_no_group_stacks(self):
        """
        If there are no stacks in a group, get_all_launch_stack_data returns
        an empty list.
        """
        eff = get_all_launch_stack_data(
            'tid',
            'gid',
            self.now,
            get_scaling_group_stacks=_constant_as_eff(('gid',), []))

        self.assertEqual(resolve_stubs(eff), {'stacks': []})
