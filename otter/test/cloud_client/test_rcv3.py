"""
Tests for otter.cloud_client.rcv3
"""

import json
from functools import partial

from effect.testing import perform_sequence

from pyrsistent import pset

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import ServiceType, service_request
from otter.cloud_client import rcv3 as r
from otter.test.cloud_client.test_init import log_intent
from otter.test.utils import (
    const, noop, patch, stub_json_response, transform_eq)
from otter.util.http import append_segments
from otter.util.pure_http import has_code


_TEST_DATA = {
    r._NODE_NOT_A_MEMBER_PATTERN: [
        ('Node d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is not a member of '
         'Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2',
         {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
          'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
        ('Node D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is not a member of '
         'Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
         {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
          'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
    ],
    r._NODE_ALREADY_A_MEMBER_PATTERN: [
        ('Cloud Server d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is already '
         'a member of Load Balancer Pool '
         'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
         {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
          'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
        ('Cloud Server D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is already '
         'a member of Load Balancer Pool '
         'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
         {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
          'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
    ],
    r._LB_INACTIVE_PATTERN: [
        ('Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 is '
         'not in an ACTIVE state',
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ('Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2 is '
         'not in an ACTIVE state',
         {"lb_id": "D95AE0C4-6AB8-4873-B82F-F8433840CFF2"})
    ],
    r._LB_DOESNT_EXIST_PATTERN: [
        ("Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 does "
         "not exist",
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ("Load Balancer Pool D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 does "
         "not exist",
         {"lb_id": "D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2"})
    ],
    r._SERVER_UNPROCESSABLE: [
        ("Cloud Server d95ae0c4-6ab8-4873-b82f-f8433840cff2 is unprocessable ",
         {"server_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ("Cloud Server D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is unprocessable ",
         {"lb_id": "D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2"})
    ]
}


class RegexTests(SynchronousTestCase):
    """
    Tests for the RCv3 error parsing regexes.
    """
    def _regex_test(self, test_pattern):
        """A generic regex test.

        Asserts that the given test pattern has test data, matches all
        of its test data, and that it does not match all of the test
        data for all of the other patterns.
        """
        self.assertIn(test_pattern, _TEST_DATA)
        for pattern, test_data in _TEST_DATA.iteritems():
            if pattern is not test_pattern:
                for message, _ in test_data:
                    self.assertIdentical(test_pattern.match(message), None)
            else:
                for message, expected_group_dict in test_data:
                    res = pattern.match(message)
                    self.assertNotIdentical(res, None)
                    self.assertEqual(res.groupdict(), expected_group_dict)

    def test_node_not_a_member_regex(self):
        """
        The regex for parsing messages saying the node isn't part of the
        load balancer parses those messages. It rejects other
        messages.
        """
        self._regex_test(r._NODE_NOT_A_MEMBER_PATTERN)

    def test_node_already_a_member_regex(self):
        """
        The regex for parsing messages saying the node is already part of
        the load balancer parses those messages. It rejects other
        messages.
        """
        self._regex_test(r._NODE_ALREADY_A_MEMBER_PATTERN)

    def test_lb_inactive_regex(self):
        """
        The regex for parsing messages saying the load balancer is
        inactive parses those messages. It rejects other messages.
        """
        self._regex_test(r._LB_INACTIVE_PATTERN)

    def test_no_such_lb_message(self):
        """
        The regex for parsing messages saying the load balancer doesn't
        exist, parses those messages. It rejects other messages.
        """
        self._regex_test(r._LB_DOESNT_EXIST_PATTERN)

    def test_server_unprocessable(self):
        """
        The regex for parsing messages saying the cloud server is
        unprocessable, parses those messages. It rejects other messages.
        """
        self._regex_test(r._SERVER_UNPROCESSABLE)


class BulkAddTests(SynchronousTestCase):

    lb_node_pairs = pset([
        ("lb-1", "node-a"),
        ("lb-1", "node-b"),
        ("lb-1", "node-c"),
        ("lb-1", "node-d"),
        ("lb-2", "node-a"),
        ("lb-2", "node-b"),
        ("lb-3", "node-c"),
        ("lb-3", "node-d")
    ])

    exp_data = [
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

    def data_eq(self, d):
        """
        Return transform_eq object for service request data for easier testing
        """
        def key_fn(e):
            return (e["load_balancer_pool"]["id"], e["cloud_server"]["id"])
        return transform_eq(partial(sorted, key=key_fn), d)

    def svc_req_intent(self, data):
        return service_request(
            ServiceType.RACKCONNECT_V3, "POST",
            "load_balancer_pools/nodes", data=data,
            success_pred=has_code(201, 409)).intent

    def setUp(self):
        patch(self, "otter.cloud_client.json.dumps",
              side_effect=lambda d, **k: ("jsonified", d))

    def test_success(self):
        """
        bulk add resulting in 201 returns Effect of None
        """
        exp_data = self.data_eq(self.exp_data)
        seq = [
            (self.svc_req_intent(exp_data), const(stub_json_response({}, 201))),
            (log_intent(
                "rcv3-bulk-request", {}, req_body=("jsonified", exp_data)),
             noop)
        ]
        self.assertIsNone(
            perform_sequence(seq, r.bulk_add(self.lb_node_pairs)))

    def test_multiple_errors(self):
        """
        If bulk add returns 409 then multiple errors returned are collected and
        raised as a single `BulkErrors`
        """
        errors = {
            "errors": [
                _TEST_DATA[r._LB_INACTIVE_PATTERN][0][0],
                _TEST_DATA[r._LB_DOESNT_EXIST_PATTERN][0][0],
                _TEST_DATA[r._SERVER_UNPROCESSABLE][0][0]
            ]
        }
        exp_data = self.data_eq(self.exp_data)
        seq = [
            (self.svc_req_intent(exp_data), const(stub_json_response(errors, 409))),
            (log_intent(
                "rcv3-bulk-request", errors, req_body=("jsonified", exp_data)),
             noop)
        ]
        with self.assertRaises(r.BulkErrors) as ec:
            perform_sequence(seq, r.bulk_add(self.lb_node_pairs))
        self.assertEqual(
            ec.exception.errors,
            pset([r.LBInactive(
                    _TEST_DATA[r._LB_INACTIVE_PATTERN][0][1]["lb_id"]),
                  r.NoSuchLBError(
                      _TEST_DATA[r._LB_DOESNT_EXIST_PATTERN][0][1]["lb_id"]),
                  r.ServerUnprocessableError(
                      _TEST_DATA[r._SERVER_UNPROCESSABLE][0][1]["server_id"])
                  ])
        )

    def test_retries(self):
        """
        If bulk adding only returns "lb node pair is already member" error with
        409 then other pairs are retried
        """
        lb_id = _TEST_DATA[r._NODE_ALREADY_A_MEMBER_PATTERN][0][1]['lb_id']
        node_id = _TEST_DATA[r._NODE_ALREADY_A_MEMBER_PATTERN][0][1]['node_id'])
        _lb_node_pairs = self.lb_node_pairs.add((lb_id, node_id))
        _exp_data = self.exp_data[:] + [{'load_balancer_pool': {'id': lb_id},
                                         'cloud_server': {'id': node_id}}]
        _eq_exp_data = self.data_eq(_exp_data)
        exp_data_retry = self.data_eq(self.exp_data)
        errors = {
            "errors": [
                _TEST_DATA[r._NODE_ALREADY_A_MEMBER_PATTERN][0][0]
            ]
        }
        seq = [
            (self.svc_req_intent(exp_data), const(stub_json_response(errors, 409))),
            (log_intent(
                "rcv3-bulk-request", errors, req_body=("jsonified", exp_data)),
             noop),
            (self.svc_req_intent(exp_data_retry), const(stub_json_response({}, 201))),
            (log_intent(
                "rcv3-bulk-request", {}, req_body=("jsonified", exp_data_retry)),
             noop)
        ]
        self.assertIsNone(perform_sequence(seq, r.bulk_add(_lb_node_pairs)))

    def test_bulk_and_retry_error(self):
        """
        If bulk adding returns "LB node already member" error along with other
        errors then there is no retry and BulkErrors is raised
        """

    def test_unknown_errors(self):
        """
        If any of the errors returned with 409 are unknown then
        `UnknownBulkResponse` is raised
        """

    def test_empty_errors(self):
        """
        If bulk add returns 409 with empty errors then `UnknownBulkResponse`
        is raised
        """
