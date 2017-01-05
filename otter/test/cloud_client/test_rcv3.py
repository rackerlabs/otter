"""
Tests for otter.cloud_client.rcv3
"""

from effect.testing import const, noop, perform_sequence

from pyrsistent import pset

from toolz.functoolz import curry

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import ServiceType, service_request
from otter.cloud_client import rcv3 as r
from otter.test.cloud_client.test_init import log_intent
from otter.test.utils import patch, stub_json_response
from otter.util.pure_http import has_code


def node_already_member(lb_id, node_id):
    return ("Cloud Server {} is already a member of "
            "Load Balancer Pool {}").format(node_id, lb_id)


def lb_inactive(lb_id):
    return "Load Balancer Pool {} is not in an ACTIVE state".format(lb_id)


def server_not_member(lb_id, server_id):
    return "Cloud Server {} is not a member of Load Balancer Pool {}".format(
        server_id, lb_id)


@curry
def rcv3_svc_req_intent(method, code, self, data):
    return service_request(
        ServiceType.RACKCONNECT_V3, method,
        "load_balancer_pools/nodes", data=data,
        success_pred=has_code(code, 409)).intent


class RCv3Tests(SynchronousTestCase):
    """
    Common data for bulk_add|delete functions
    """

    lbs = ["a6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2",
           "b6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2",
           "c6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"]
    nodes = ["a95ae0c4-6ab8-4873-b82f-f8433840cff2",
             "b95ae0c4-6ab8-4873-b82f-f8433840cff2",
             "c95ae0c4-6ab8-4873-b82f-f8433840cff2"]
    pairs = pset(zip(lbs, nodes))
    data = r._sorted_data(pairs)

    def setUp(self):
        patch(self, "otter.cloud_client.json.dumps",
              side_effect=lambda d, **k: ("jsonified", d))


class BulkAddTests(RCv3Tests):

    svc_req_intent = rcv3_svc_req_intent("POST", 201)

    def test_success(self):
        """
        bulk add resulting in 201 returns Effect of None
        """
        resp = {"resp": "yo"}
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(resp, 201))),
            (log_intent(
                "request-rcv3-bulk", resp, req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertEqual(perform_sequence(seq, r.bulk_add(self.pairs)), resp)

    def test_multiple_errors(self):
        """
        If bulk add returns 409 then multiple errors returned are collected and
        raised as a single `BulkErrors`
        """
        errors = {
            "errors": [
                lb_inactive(self.lbs[0]),
                "Load Balancer Pool {} does not exist".format(self.lbs[1]),
                "Cloud Server {} is unprocessable".format(self.nodes[2])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        with self.assertRaises(r.BulkErrors) as ec:
            perform_sequence(seq, r.bulk_add(self.pairs))
        self.assertEqual(
            ec.exception.errors,
            pset([r.LBInactive(self.lbs[0]),
                  r.NoSuchLBError(self.lbs[1]),
                  r.ServerUnprocessableError(self.nodes[2])])
        )

    def _check_retries(self, pairs, data, retried_data, errors):
        resp = {"response": "yo"}
        seq = [
            (self.svc_req_intent(data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", data)),
             noop),
            (self.svc_req_intent(retried_data),
             const(stub_json_response(resp, 201))),
            (log_intent(
                "request-rcv3-bulk", resp,
                req_body=("jsonified", retried_data)),
             noop)
        ]
        self.assertEqual(perform_sequence(seq, r.bulk_add(pairs)), resp)

    def test_retries(self):
        """
        If bulk adding only returns "lb node pair is already member" error with
        409 then other pairs are retried
        """
        errors = {
            "errors": [
                node_already_member(self.lbs[0].upper(), self.nodes[0])
            ]
        }
        retried_data = r._sorted_data(
            self.pairs - pset([(self.lbs[0], self.nodes[0])]))
        self._check_retries(self.pairs, self.data, retried_data, errors)

    def test_retries_uppercase(self):
        """
        If bulk adding is called with upper case LB ID and it only returns
        "lb node pair is already member" error with 409 then other pairs
        are retried
        """
        lbs = self.lbs[:]
        lbs[0] = lbs[0].upper()
        pairs = pset(zip(lbs, self.nodes))
        retried_data = r._sorted_data(
            pairs - pset([(lbs[0], self.nodes[0])]))
        errors = {
            "errors": [
                node_already_member(lbs[0], self.nodes[0])
            ]
        }
        self._check_retries(pairs, self.data, retried_data, errors)

    def test_all_already_member(self):
        """
        If bulk_add returns 409 with all attempted pairs as "lb node already
        member" then it will return None
        """
        errors = {
            "errors": [
                node_already_member(lb.upper(), node)
                for lb, node in self.pairs
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertIsNone(perform_sequence(seq, r.bulk_add(self.pairs)))

    def test_bulk_and_retry_error(self):
        """
        If bulk adding returns "LB node already member" error along with other
        errors then there is no retry and BulkErrors is raised
        """
        errors = {
            "errors": [
                node_already_member(self.lbs[0].upper(), self.nodes[0]),
                lb_inactive(self.lbs[1])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        with self.assertRaises(r.BulkErrors) as ec:
            perform_sequence(seq, r.bulk_add(self.pairs))
        self.assertEqual(
            ec.exception.errors, pset([r.LBInactive(self.lbs[1])]))

    def test_unknown_errors(self):
        """
        If any of the errors returned with 409 are unknown then
        `UnknownBulkResponse` is raised
        """
        errors = {
            "errors": [
                "unknown error",
                lb_inactive(self.lbs[0])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertRaises(
            r.UnknownBulkResponse, perform_sequence, seq,
            r.bulk_add(self.pairs))

    def test_empty_errors(self):
        """
        If bulk add returns 409 with empty errors then `UnknownBulkResponse`
        is raised
        """
        errors = {"errors": []}
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertRaises(
            r.UnknownBulkResponse, perform_sequence, seq,
            r.bulk_add(self.pairs))


class BulkDeleteTests(RCv3Tests):
    """
    Tests for :func:`bulk_delete"
    """

    svc_req_intent = rcv3_svc_req_intent("DELETE", 204)

    def test_success(self):
        """
        bulk_delete resulting in 204 returns Effect of None
        """
        resp = {"response": "yo!"}
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(resp, 204))),
            (log_intent(
                "request-rcv3-bulk", resp, req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertEqual(
            perform_sequence(seq, r.bulk_delete(self.pairs)), resp)

    def test_lb_inactive(self):
        """
        If bulk_delete returns 409 with only LB inactive errors then it raises
        `BulkErrors` with LBInActive errors in it
        """
        errors = {
            "errors": [
                lb_inactive(self.lbs[0]), lb_inactive(self.lbs[1])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        with self.assertRaises(r.BulkErrors) as ec:
            perform_sequence(seq, r.bulk_delete(self.pairs))
        self.assertEqual(
            ec.exception.errors,
            pset([r.LBInactive(self.lbs[0]), r.LBInactive(self.lbs[1])])
        )

    def _check_retries(self, get_pairs_data):
        errors = {
            "errors": [
                server_not_member(self.lbs[0].upper(), self.nodes[0]),
                "Cloud Server {} does not exist".format(self.nodes[1]),
                "Load Balancer Pool {} does not exist".format(
                    self.lbs[2].upper())
            ]
        }
        lbr1 = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        noder1 = "a95ae0c4-6ab8-4873-b82f-f8433840cff2"
        lbr2 = "e6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        noder2 = "e95ae0c4-6ab8-4873-b82f-f8433840cff2"
        pairs, data = get_pairs_data(lbr1, noder1, lbr2, noder2)
        retried_data = r._sorted_data([(lbr1, noder1), (lbr2, noder2)])
        success_resp = {"good": "response"}
        seq = [
            (self.svc_req_intent(data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors, req_body=("jsonified", data)),
             noop),
            (self.svc_req_intent(retried_data),
             const(stub_json_response(success_resp, 204))),
            (log_intent(
                "request-rcv3-bulk", success_resp,
                req_body=("jsonified", retried_data)),
             noop)
        ]
        self.assertEqual(
            perform_sequence(seq, r.bulk_delete(pairs)), success_resp)

    def test_retries(self):
        """
        If bulk_delete only returns "server not a member", lb or server deleted
        error(s) with 409 then other pairs are retried
        """
        def get_pairs_data(lbr1, noder1, lbr2, noder2):
            pairs = pset(
                [(self.lbs[0], self.nodes[1]),  # test same server pairs
                 (self.lbs[2], self.nodes[0]),  # test same lb pairs
                 (lbr1, noder1), (lbr2, noder2)])
            pairs |= self.pairs
            return pairs, r._sorted_data(pairs)
        self._check_retries(get_pairs_data)

    def test_retries_uppercase(self):
        """
        If bulk_delete is called with upper case LB ID and it only returns
        "server not a member", lb or server deleted error(s) with 409 then
        other pairs are retried
        """
        def get_pairs_data(lbr1, noder1, lbr2, noder2):
            new_pairs = pset(
                [(self.lbs[0], self.nodes[1]),  # test same server pairs
                 (self.lbs[2], self.nodes[0]),  # test same lb pairs
                 (lbr1, noder1), (lbr2, noder2)])
            # existing pairs with upper case LB
            lbs = self.lbs[:]
            lbs[0] = lbs[0].upper()
            existing_pairs = pset(zip(lbs, self.nodes))
            pairs = existing_pairs | new_pairs
            # The data will still be self.pairs since lbs[0] will be normalized
            return pairs, r._sorted_data(self.pairs | new_pairs)
        self._check_retries(get_pairs_data)

    def test_all_retries(self):
        """
        If bulk_delete returns "server not a member", lb or server deleted
        for all attempted pairs then there is no retry and returns None
        """
        errors = {
            "errors": [
                server_not_member(self.lbs[0].upper(), self.nodes[0]),
                "Cloud Server {} does not exist".format(self.nodes[1]),
                "Load Balancer Pool {} does not exist".format(
                    self.lbs[2].upper())
            ]
        }
        pairs = pset([
            (self.lbs[0], self.nodes[1]),  # test same server pairs
            (self.lbs[2], self.nodes[0])   # test same lb pairs
        ])
        pairs = self.pairs | pairs
        data = r._sorted_data(pairs)
        seq = [
            (self.svc_req_intent(data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors, req_body=("jsonified", data)),
             noop)
        ]
        self.assertIsNone(perform_sequence(seq, r.bulk_delete(pairs)))

    def test_lb_inactive_and_retry_error(self):
        """
        If bulk_delete returns lb inactive along with any other errors then
        there is no retry and BulkErrors is raised
        """
        errors = {
            "errors": [
                lb_inactive(self.lbs[0]),
                server_not_member(self.lbs[1], self.nodes[1]),
                server_not_member(self.lbs[1].upper(), self.nodes[1])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        with self.assertRaises(r.BulkErrors) as ec:
            perform_sequence(seq, r.bulk_delete(self.pairs))
        self.assertEqual(
            ec.exception.errors, pset([r.LBInactive(self.lbs[0])]))

    def test_unknown_errors(self):
        """
        If any of the errors returned with 409 are unknown then
        `UnknownBulkResponse` is raised
        """
        errors = {
            "errors": [
                "unknown error",
                lb_inactive(self.lbs[0])
            ]
        }
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertRaises(
            r.UnknownBulkResponse, perform_sequence, seq,
            r.bulk_delete(self.pairs))

    def test_empty_errors(self):
        """
        If bulk_delete returns 409 with empty errors then `UnknownBulkResponse`
        is raised
        """
        errors = {"errors": []}
        seq = [
            (self.svc_req_intent(self.data),
             const(stub_json_response(errors, 409))),
            (log_intent(
                "request-rcv3-bulk", errors,
                req_body=("jsonified", self.data)),
             noop)
        ]
        self.assertRaises(
            r.UnknownBulkResponse, perform_sequence, seq,
            r.bulk_delete(self.pairs))
