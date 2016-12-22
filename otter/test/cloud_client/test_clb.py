"""Tests for otter.cloud_client.clb"""

import json

from effect import sync_perform
from effect.testing import EQFDispatcher, perform_sequence

import six

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import service_request
from otter.cloud_client.clb import (
    CLBDeletedError,
    CLBDuplicateNodesError,
    CLBImmutableError,
    CLBNodeLimitError,
    CLBNotActiveError,
    CLBPartialNodesRemoved,
    CLBRateLimitError,
    CLB_BATCH_DELETE_LIMIT,
    NoSuchCLBError,
    NoSuchCLBNodeError,
    add_clb_nodes,
    change_clb_node,
    get_clb_health_monitor,
    get_clb_node_feed,
    get_clb_nodes,
    get_clbs,
    remove_clb_nodes)
from otter.constants import ServiceType
from otter.test.cloud_client.test_init import log_intent, service_request_eqf
from otter.test.utils import (
    StubResponse,
    const,
    intent_func,
    noop,
    stub_json_response,
    stub_pure_response
)
from otter.util.http import APIError
from otter.util.pure_http import has_code


def assert_parses_common_clb_errors(testcase, intent, eff, lb_id):
    """
    Assert that the effect produced performs the common CLB error parsing:
    :class:`CLBImmutableError`, :class:`CLBDescription`,
    :class:`NoSuchCLBError`, :class:`CLBRateLimitError`,
    :class:`APIError`

    :param :obj:`twisted.trial.unittest.TestCase` testcase: Test object
    :param intent: expected ``ServiceRequest`` intent
    :param eff: Effect returned from function being tested
    :param lb_id: ID of load balancer being accessed in the function being
        tested
    """
    json_responses_and_errs = [
        ("Load Balancer '{0}' has a status of 'BUILD' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'PENDING_UPDATE' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'unexpected status' and is "
         "considered immutable.", 422, CLBImmutableError),
        ("Load Balancer '{0}' has a status of 'PENDING_DELETE' and is "
         "considered immutable.", 422, CLBDeletedError),
        ("The load balancer is deleted and considered immutable.",
         422, CLBDeletedError),
        ("Load balancer not found.", 404, NoSuchCLBError),
        ("LoadBalancer is not ACTIVE", 422, CLBNotActiveError),
        ("The loadbalancer is marked as deleted.", 410, CLBDeletedError),
    ]

    for msg, code, err in json_responses_and_errs:
        msg = msg.format(lb_id)
        resp = stub_pure_response(
            json.dumps({'message': msg, 'code': code, 'details': ''}),
            code)
        with testcase.assertRaises(err) as cm:
            perform_sequence([(intent, service_request_eqf(resp))], eff)
        testcase.assertEqual(cm.exception,
                             err(msg, lb_id=six.text_type(lb_id)))

    # OverLimit Retry is different because it's produced by repose
    over_limit = stub_pure_response(
        json.dumps({
            "overLimit": {
                "message": "OverLimit Retry...",
                "code": 413,
                "retryAfter": "2015-06-13T22:30:10Z",
                "details": "Error Details..."
            }
        }),
        413)
    with testcase.assertRaises(CLBRateLimitError) as cm:
        perform_sequence([(intent, service_request_eqf(over_limit))], eff)
    testcase.assertEqual(
        cm.exception,
        CLBRateLimitError("OverLimit Retry...",
                          lb_id=six.text_type(lb_id)))

    # Ignored errors
    bad_resps = [
        stub_pure_response(
            json.dumps({
                'message': ("Load Balancer '{0}' has a status of 'BROKEN' "
                            "and is considered immutable."),
                'code': 422}),
            422),
        stub_pure_response(
            json.dumps({
                'message': ("The load balancer is deleted and considered "
                            "immutable"),
                'code': 404}),
            404),
        stub_pure_response(
            json.dumps({
                'message': "Cloud load balancers is down",
                'code': 500}),
            500),
        stub_pure_response(
            json.dumps({
                'message': "this is not an over limit message",
                'code': 413}),
            413),
        stub_pure_response("random repose error message", 404),
        stub_pure_response("random repose error message", 413)
    ]

    for resp in bad_resps:
        with testcase.assertRaises(APIError) as cm:
            perform_sequence([(intent, service_request_eqf(resp))], eff)
        testcase.assertEqual(
            cm.exception,
            APIError(headers={}, code=resp[0].code, body=resp[1],
                     method='method', url='original/request/URL'))


class CLBClientTests(SynchronousTestCase):
    """
    Tests for CLB client functions, such as :obj:`change_clb_node`.
    """
    @property
    def lb_id(self):
        """What is my LB ID"""
        return "123456"

    def test_change_clb_node(self):
        """
        Produce a request for modifying a node on a load balancer, which
        returns a successful result on 202.

        Parse the common CLB errors, and :class:`NoSuchCLBNodeError`.
        """
        eff = change_clb_node(lb_id=self.lb_id, node_id='1234',
                              condition="DRAINING", weight=50,
                              _type='SECONDARY')
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            'loadbalancers/{0}/nodes/1234'.format(self.lb_id),
            data={'node': {'condition': 'DRAINING',
                           'weight': 50, 'type': 'SECONDARY'}},
            success_pred=has_code(202))

        # success
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('', 202)))])
        self.assertEqual(sync_perform(dispatcher, eff),
                         stub_pure_response(None, 202))

        # NoSuchCLBNode failure
        msg = "Node with id #1234 not found for loadbalancer #{0}".format(
            self.lb_id)
        no_such_node = stub_pure_response(
            json.dumps({'message': msg, 'code': 404}), 404)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(no_such_node))])

        with self.assertRaises(NoSuchCLBNodeError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            NoSuchCLBNodeError(msg, lb_id=six.text_type(self.lb_id),
                               node_id=u'1234'))

        # all the common failures
        assert_parses_common_clb_errors(self, expected.intent, eff, "123456")

    def test_change_clb_node_default_type(self):
        """
        Produce a request for modifying a node on a load balancer with the
        default type, which returns a successful result on 202.
        """
        eff = change_clb_node(lb_id=self.lb_id, node_id='1234',
                              condition="DRAINING", weight=50)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            'loadbalancers/{0}/nodes/1234'.format(self.lb_id),
            data={'node': {'condition': 'DRAINING',
                           'weight': 50, 'type': 'PRIMARY'}},
            success_pred=has_code(202))

        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('', 202)))])
        self.assertEqual(sync_perform(dispatcher, eff),
                         stub_pure_response(None, 202))

    def test_add_clb_nodes(self):
        """
        Produce a request for adding nodes to a load balancer, which returns
        a successful result on a 202.

        Parse the common CLB errors, and a :class:`CLBDuplicateNodesError`.
        """
        nodes = [{"address": "1.1.1.1", "port": 80, "condition": "ENABLED"},
                 {"address": "1.1.1.2", "port": 80, "condition": "ENABLED"},
                 {"address": "1.1.1.5", "port": 81, "condition": "ENABLED"}]

        eff = add_clb_nodes(lb_id=self.lb_id, nodes=nodes)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            'loadbalancers/{0}/nodes'.format(self.lb_id),
            data={'nodes': nodes},
            success_pred=has_code(202))

        # success
        seq = [
            (expected.intent, lambda i: stub_json_response({}, 202, {})),
            (log_intent('request-add-clb-nodes', {}), lambda _: None)]
        self.assertEqual(perform_sequence(seq, eff),
                         (StubResponse(202, {}), {}))

        # CLBDuplicateNodesError failure
        msg = ("Duplicate nodes detected. One or more nodes already "
               "configured on load balancer.")
        duplicate_nodes = stub_pure_response(
            json.dumps({'message': msg, 'code': 422}), 422)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(duplicate_nodes))])

        with self.assertRaises(CLBDuplicateNodesError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            CLBDuplicateNodesError(msg, lb_id=six.text_type(self.lb_id)))

        # CLBNodeLimitError failure
        msg = "Nodes must not exceed 25 per load balancer."
        limit = stub_pure_response(
            json.dumps({'message': msg, 'code': 413}), 413)
        dispatcher = EQFDispatcher([(
            expected.intent, service_request_eqf(limit))])

        with self.assertRaises(CLBNodeLimitError) as cm:
            sync_perform(dispatcher, eff)
        self.assertEqual(
            cm.exception,
            CLBNodeLimitError(msg, lb_id=six.text_type(self.lb_id),
                              node_limit=25))

        # all the common failures
        assert_parses_common_clb_errors(self, expected.intent, eff, "123456")

    def expected_node_removal_req(self, nodes=(1, 2)):
        """
        :return: Expected effect for a node removal request.
        """
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            'loadbalancers/{}/nodes'.format(self.lb_id),
            params={'id': map(str, nodes)},
            success_pred=has_code(202))

    def test_remove_clb_nodes_success(self):
        """
        A DELETE request is sent, and the Effect returns None if 202 is
        returned.
        """
        eff = remove_clb_nodes(self.lb_id, ["1", "2"])
        seq = [
            (self.expected_node_removal_req().intent,
             service_request_eqf(stub_pure_response({}, 202))),
        ]
        result = perform_sequence(seq, eff)
        self.assertIs(result, None)

    def test_remove_clb_nodes_handles_standard_clb_errors(self):
        """
        Common CLB errors about it being in a deleted state, pending update,
        etc. are handled.
        """
        eff = remove_clb_nodes(self.lb_id, ["1", "2"])
        assert_parses_common_clb_errors(
            self, self.expected_node_removal_req().intent, eff, "123456")

    def test_remove_clb_nodes_non_202(self):
        """Any random HTTP response code is bubbled up as an APIError."""
        eff = remove_clb_nodes(self.lb_id, ["1", "2"])
        seq = [
            (self.expected_node_removal_req().intent,
             service_request_eqf(stub_pure_response({}, 200))),
        ]
        self.assertRaises(APIError, perform_sequence, seq, eff)

    def test_remove_clb_nodes_random_400(self):
        """Random 400s that can't be parsed are bubbled up as an APIError."""
        error_bodies = [
            {'validationErrors': {'messages': ['bar']}},
            {'messages': 'bar'},
            {'validationErrors': {'messages': []}},
            "random non-json"
        ]
        for body in error_bodies:
            eff = remove_clb_nodes(self.lb_id, ["1", "2"])
            seq = [
                (self.expected_node_removal_req().intent,
                 service_request_eqf(stub_pure_response(body, 400))),
            ]
            self.assertRaises(APIError, perform_sequence, seq, eff)

    def test_remove_clb_nodes_retry_on_some_invalid_nodes(self):
        """
        When CLB returns an error indicating that some of the nodes are
        invalid, the request is retried without the offending nodes.
        """
        node_ids = map(str, range(1, 5))
        eff = remove_clb_nodes(self.lb_id, node_ids)
        response = stub_pure_response(
            {'validationErrors': {'messages': [
                'Node ids 1,3 are not a part of your loadbalancer']}},
            400)
        response2 = stub_pure_response({}, 202)
        seq = [
            (self.expected_node_removal_req(node_ids).intent,
             service_request_eqf(response)),
            (self.expected_node_removal_req(["2", "4"]).intent,
             service_request_eqf(response2))
        ]
        self.assertIs(perform_sequence(seq, eff), None)

    def test_remove_clb_nodes_partial_success(self):
        """
        ``remove_clb_nodes`` removes only CLB_BATCH_DELETE_LIMIT nodes and
        raises ``CLBPartialNodesRemoved`` with remaining nodes
        """
        limit = CLB_BATCH_DELETE_LIMIT
        node_ids = map(str, range(limit + 2))
        removed = map(six.text_type, range(limit))
        not_removed = map(six.text_type, range(limit, limit + 2))
        eff = remove_clb_nodes(self.lb_id, node_ids)
        seq = [
            (self.expected_node_removal_req(removed).intent,
             service_request_eqf(stub_pure_response({}, 202))),
        ]
        with self.assertRaises(CLBPartialNodesRemoved) as ce:
            perform_sequence(seq, eff)
        self.assertEqual(
            ce.exception,
            CLBPartialNodesRemoved(
                six.text_type(self.lb_id), not_removed, removed))

    def test_get_clbs(self):
        """Returns all the load balancer details from the LBs endpoint."""
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS, 'GET', 'loadbalancers')
        req = get_clbs()
        body = {'loadBalancers': 'lbs!'}
        seq = [
            (expected.intent, lambda i: stub_json_response(body)),
            (log_intent('request-list-clbs', body), lambda _: None)]
        self.assertEqual(perform_sequence(seq, req), 'lbs!')

    def test_get_clb_nodes(self):
        """:func:`get_clb_nodes` returns all the nodes for a LB."""
        req = get_clb_nodes(self.lb_id)
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'GET', 'loadbalancers/123456/nodes')
        body = {'nodes': 'nodes!'}
        seq = [
            (expected.intent, lambda i: stub_json_response(body)),
            (log_intent('request-list-clb-nodes', body), lambda _: None)]
        self.assertEqual(perform_sequence(seq, req), 'nodes!')

    def test_get_clb_nodes_error_handling(self):
        """:func:`get_clb_nodes` parses the common CLB errors."""
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'GET', 'loadbalancers/123456/nodes')
        assert_parses_common_clb_errors(
            self, expected.intent, get_clb_nodes(self.lb_id), "123456")

    def test_get_clb_health_mon(self):
        """
        :func:`get_clb_health_monitor` calls
        ``GET .../loadbalancers/lb_id/healthmonitor`` and returns setting
        inside {"healthMonitor": ...}
        """
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'GET', 'loadbalancers/123456/healthmonitor')
        settings = {
            "type": "CONNECT",
            "delay": 10,
            "timeout": 10,
            "attemptsBeforeDeactivation": 3
        }
        body = {"healthMonitor": settings}
        seq = [
            (expected.intent, const(stub_json_response(body))),
            (log_intent('request-get-clb-healthmon', body), noop)
        ]
        self.assertEqual(
            perform_sequence(seq, get_clb_health_monitor(self.lb_id)),
            settings)

    def test_get_clb_health_mon_error(self):
        """
        :func:`get_clb_health_monitor` parses the common CLB errors.
        """
        expected = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS, 'GET',
            'loadbalancers/123456/healthmonitor')
        assert_parses_common_clb_errors(
            self, expected.intent, get_clb_health_monitor(self.lb_id),
            self.lb_id)


class GetCLBNodeFeedTests(SynchronousTestCase):
    """
    Tests for :func:`get_clb_node_feed`
    """

    def test_calls_read_entries(self):
        """
        Calls `cf.read_entries` with CLB servicetype and atom URL and returns
        the feed part of the result
        """
        from otter.cloud_client.clb import cf
        self.patch(cf, "read_entries", intent_func("re"))
        eff = get_clb_node_feed("12", "13")
        seq = [
            (("re", ServiceType.CLOUD_LOAD_BALANCERS,
              "loadbalancers/12/nodes/13.atom", {}, cf.Direction.NEXT,
              "request-get-clb-node-feed"),
             const((["feed1"], {"param": "2"})))
        ]
        self.assertEqual(perform_sequence(seq, eff), ["feed1"])

    def test_error_handling(self):
        """
        Parses regular CLB errors and raises corresponding exceptions
        """
        svc_intent = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS, "GET",
            "loadbalancers/12/nodes/13.atom", params={},
            json_response=False).intent
        assert_parses_common_clb_errors(
            self, svc_intent, get_clb_node_feed("12", "13"), "12")
