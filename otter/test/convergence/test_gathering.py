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
from effect.testing import (
    EQDispatcher, EQFDispatcher, Stub)

import mock

from pyrsistent import freeze

from toolz.curried import map
from toolz.functoolz import compose

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import NoSuchEndpoint
from otter.cloud_client import CLBDeletedError, NoSuchCLBError, service_request
from otter.constants import ServiceType
from otter.convergence.gathering import (
    UnexpectedBehaviorError,
    extract_CLB_drained_at,
    get_all_convergence_data,
    get_all_server_details,
    get_all_scaling_group_servers,
    get_clb_contents,
    get_rcv3_contents,
    get_scaling_group_servers,
    merge_servers)
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
    raise_,
    resolve_effect,
    resolve_retry_stubs,
    resolve_stubs,
    server
)
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
                   method, url, headers=None, data=None):
    expected_eff = service_request(
        service_type, method, url, headers=headers, data=data)
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
    return (ServiceType.CLOUD_SERVERS, 'GET',
            'servers/detail?{}'.format(urlencode(sorted(params.items()))))


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
        eff = get_all_server_details(batch_size=10)
        svcreq = resolve_retry_stubs(eff)
        result = resolve_svcreq(
            svcreq, (fake_response, body), *svc_request_args(limit=10))
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
        result = resolve_svcreq(
            svcreq, (fake_response, body), *svc_request_args(limit=10))
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
        result = resolve_svcreq(
            svcreq, (fake_response, body), *svc_request_args(limit=10))
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?limit=10&marker=19',
                    'rel': 'next'}]}
        result = resolve_svcreq(
            next_req, (fake_response, body),
            *svc_request_args(limit=10, marker=9))
        self.assertIsInstance(result, Effect)

        # third request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': []}
        result = resolve_svcreq(next_req, (fake_response, body),
                                *svc_request_args(limit=10, marker=19))

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
        result = resolve_svcreq(svcreq, (fake_response, body),
                                *svc_request_args(limit=10))
        self.assertIsInstance(result, Effect)

        # next request, because previous had a next link
        next_req = resolve_retry_stubs(result)
        body = {'servers': servers[10:],
                'servers_links': [{
                    'href': 'https://ignoreme/path?anything=1',
                    'rel': 'next'}]}
        self.assertRaises(UnexpectedBehaviorError,
                          resolve_svcreq, next_req, (fake_response, body),
                          *svc_request_args(anything=1))

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
            svcreq, (fake_response, body),
            *svc_request_args(changes_since=since, limit=10))
        self.assertEqual(result, self.servers)

    def test_retry(self):
        """The HTTP requests are retried with some appropriate policy."""
        eff = get_all_server_details(batch_size=10)
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(5),
                                next_interval=exponential_backoff_interval(2)))


class GetAllScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_scaling_group_servers`
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
            get_all_scaling_group_servers(changes_since=since))
        fake_response = object()
        body = {'servers': []}
        result = resolve_svcreq(
            eff, (fake_response, body),
            *svc_request_args(changes_since=since, limit=100))
        self.assertEqual(result, {})

    def test_filters_no_metadata(self):
        """
        Servers without metadata are not included in the result.
        """
        servers = [{'id': i} for i in range(10)]
        eff = resolve_retry_stubs(get_all_scaling_group_servers())
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
        eff = resolve_retry_stubs(get_all_scaling_group_servers())
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
        eff = resolve_retry_stubs(get_all_scaling_group_servers())
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
            get_all_scaling_group_servers(
                server_predicate=lambda s: s['id'] % 3 == 0))
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
        asmetakey = "rax:autoscale:group:id"
        self.servers1 = [
            {'id': 'a', 'metadata': {asmetakey: "gid"}},
            {'id': 'b', 'metadata': {asmetakey: "gid"}},
            {'id': 'd', 'metadata': {asmetakey: "gid"}}]
        self.servers2 = [
            {'id': 'a', 'b': 'c', 'metadata': {asmetakey: "gid"}},
            {'id': 'd', 'metadata': {"changed": "yes"}}]
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

    def test_old_cache(self):
        """
        If cache is older than 30 days then servers returned are got by getting
        current list and changes since last 30 days.
        """
        last_update = datetime(2010, 3, 1)
        exp_last_update = datetime(2010, 5, 1)
        changes = self.servers1
        current = self.servers2
        sequence = [
            (("cachegstidgid", False), lambda i: (object(), last_update)),
            nested_parallel([
                (("alls", exp_last_update), lambda i: changes),
                (("alls",), lambda i: current)
            ])
        ]
        self.assertEqual(
            self.freeze(perform_sequence(sequence, self._invoke())),
            self.freeze([changes[1], current[0]]))

    def test_from_cache(self):
        """
        If cache is < 30 days old then servers returned are merge of
        changes since the cache time
        """
        cache = self.servers1
        changes = self.servers2
        last_update = datetime(2010, 5, 20)
        sequence = [
            (("cachegstidgid", False), lambda i: (cache, last_update)),
            (("alls", last_update), lambda i: changes)]
        self.assertEqual(
            self.freeze(perform_sequence(sequence, self._invoke())),
            self.freeze([cache[1], changes[0]]))

    def test_merge_servers_precedence(self):
        """
        In :func:`merge_servers`, if first list has common servers with second
        list, the second one takes precedence
        """
        first = [{'id': 'a', 'a': 1}, {'id': 'b', 'b': 2}]
        second = [{'id': 'd', 'd': 3}, {'id': 'b', 'b': 4}]
        self.assertEqual(
            self.freeze(merge_servers(first, second)),
            self.freeze([first[0]] + second))


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
        """mock `extract_CLB_drained_at`"""
        self.feeds = {'11feed': 1.0, '22feed': 2.0}
        self.mock_eda = patch(
            self, 'otter.convergence.gathering.extract_CLB_drained_at',
            side_effect=lambda f: self.feeds[f])

    def lb_req(self, method, url, json_response, response):
        """
        Return a SequenceDispatcher two-tuple to match a service request and
        specify the result.
        """
        if isinstance(response, Exception):
            handler = lambda i: raise_(response)
        else:
            handler = lambda i: (StubResponse(200, {}), response)
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
                    method, url, json_response=json_response).intent,
                 handler)
            ])
        )

    def test_success(self):
        """
        Gets LB contents with drained_at correctly
        """
        seq = [
            self.lb_req(
                'GET', 'loadbalancers', True,
                {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes', True,
                    {'nodes': [
                        {'id': '11', 'port': 20, 'address': 'a11',
                         'weight': 2, 'condition': 'DRAINING',
                         'type': 'PRIMARY'},
                        {'id': '12', 'port': 20, 'address': 'a12',
                         'weight': 2, 'condition': 'ENABLED',
                         'type': 'PRIMARY'}]}
                ),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes', True,
                    {'nodes': [
                        {'id': '21', 'port': 20, 'address': 'a21',
                         'weight': 3, 'condition': 'ENABLED',
                         'type': 'PRIMARY'},
                        {'id': '22', 'port': 20, 'address': 'a22',
                         'condition': 'DRAINING', 'type': 'PRIMARY'}]}),
            ]),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes/11.atom', False, '11feed'),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes/22.atom', False, '22feed'),
            ]),
        ]
        eff = get_clb_contents()
        draining, enabled = CLBNodeCondition.DRAINING, CLBNodeCondition.ENABLED
        make_desc = partial(CLBDescription, port=20, type=CLBNodeType.PRIMARY)
        self.assertEqual(
            perform_sequence(seq, eff),
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
                                           weight=1,
                                           condition=draining))])

    def test_no_lb(self):
        """
        Return empty list if there are no LB
        """
        seq = [
            self.lb_req('GET', 'loadbalancers', True,
                        {'loadBalancers': []}),
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
            self.lb_req('GET', 'loadbalancers', True,
                        {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                self.lb_req('GET', 'loadbalancers/1/nodes', True,
                            {'nodes': []}),
                self.lb_req('GET', 'loadbalancers/2/nodes', True,
                            {'nodes': []}),
            ]),
            nested_parallel([]),  # No nodes to fetch
        ]
        self.assertEqual(perform_sequence(seq, get_clb_contents()), [])

    def test_no_draining(self):
        """
        Doesnt fetch feeds if all nodes are ENABLED
        """
        seq = [
            self.lb_req('GET', 'loadbalancers', True,
                        {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes', True,
                    {'nodes': [
                        {'id': '11', 'port': 20, 'address': 'a11',
                         'weight': 2, 'condition': 'ENABLED',
                         'type': 'PRIMARY'}]}),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes', True,
                    {'nodes': [
                        {'id': '21', 'port': 20, 'address': 'a21',
                         'weight': 2, 'condition': 'ENABLED',
                         'type': 'PRIMARY'}]}),
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
                     description=make_desc(lb_id='1')),
             CLBNode(node_id='21', address='a21',
                     description=make_desc(lb_id='2'))])

    def test_lb_disappeared_during_node_fetch(self):
        """
        If a load balancer gets deleted while fetching nodes, no nodes will be
        returned for it.
        """
        seq = [
            self.lb_req('GET', 'loadbalancers', True,
                        {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes', True,
                    {'nodes': [
                        {'id': '11', 'port': 20, 'address': 'a11',
                         'weight': 2, 'condition': 'ENABLED',
                         'type': 'PRIMARY'}]}),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes', True,
                    CLBDeletedError(lb_id=u'2')),
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
        seq = [
            self.lb_req(
                'GET', 'loadbalancers', True,
                {'loadBalancers': [{'id': 1}, {'id': 2}]}),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes', True,
                    {'nodes': [
                        {'id': '11', 'port': 20, 'address': 'a11',
                         'condition': 'DRAINING', 'type': 'PRIMARY'},
                        {'id': '12', 'port': 20, 'address': 'a12',
                         'condition': 'ENABLED', 'type': 'PRIMARY'}]}
                ),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes', True,
                    {'nodes': [
                        {'id': '21', 'port': 20, 'address': 'a21',
                         'condition': 'DRAINING', 'type': 'PRIMARY'}]}),
            ]),
            nested_parallel([
                self.lb_req(
                    'GET', 'loadbalancers/1/nodes/11.atom', False,
                    CLBDeletedError(lb_id=u'1')),
                self.lb_req(
                    'GET', 'loadbalancers/2/nodes/21.atom', False, '22feed'),
            ]),
        ]
        eff = get_clb_contents()
        draining, enabled = CLBNodeCondition.DRAINING, CLBNodeCondition.ENABLED
        make_desc = partial(CLBDescription, port=20, type=CLBNodeType.PRIMARY)
        self.assertEqual(
            perform_sequence(seq, eff),
            [CLBNode(node_id='21',
                     address='a21',
                     drained_at=2.0,
                     description=make_desc(lb_id='2',
                                           condition=draining))])


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
