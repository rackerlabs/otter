"""Tests for convergence steps."""
import json

from effect import Func, sync_perform
from effect.testing import EQDispatcher

from mock import ANY

from pyrsistent import freeze, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.model import CLBDescription, StepResult
from otter.convergence.steps import (
    AddNodesToCLB,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    CreateServer,
    DeleteServer,
    RemoveNodesFromCLB,
    SetMetadataItemOnServer,
    _RCV3_LB_DOESNT_EXIST_PATTERN,
    _RCV3_LB_INACTIVE_PATTERN,
    _RCV3_NODE_ALREADY_A_MEMBER_PATTERN,
    _RCV3_NODE_NOT_A_MEMBER_PATTERN,
    _rcv3_check_bulk_add,
    _rcv3_check_bulk_delete)
from otter.http import has_code, service_request
from otter.test.utils import StubResponse, resolve_effect
from otter.util.hashkey import generate_server_name
from otter.util.http import APIError


def service_request_error_response(error):
    """
    Returns the error response that gets passed to error handlers on the
    service request effect.

    That is, (type of error, actual error, traceback object)

    Just returns None for the traceback object.
    """
    return (type(error), error, None)


class CreateServerTests(SynchronousTestCase):
    """
    Tests for :obj:`CreateServer.as_effect`.
    """

    def test_create_server_request_with_name(self):
        """
        :obj:`CreateServer.as_effect` produces a request for creating a server.
        If the name is given, a randomly generated suffix is appended to the
        server name.
        """
        create = CreateServer(
            server_config=freeze({'server': {'name': 'myserver',
                                             'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'myserver-random-name',
                                 'flavorRef': '1'}},
                success_pred=has_code(202),
                reauth_codes=(401,)).intent)

    def test_create_server_noname(self):
        """
        :obj:`CreateServer.as_effect`, when no name is provided in the launch
        config, will generate the name will from scratch.

        This only verifies intent; result reporting is tested in
        :meth:`test_create_server`.
        """
        create = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'random-name', 'flavorRef': '1'}},
                success_pred=has_code(202),
                reauth_codes=(401,)).intent)

    def test_create_server_success_case(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a successful create,
        returns with :obj:`StepResult.SUCCESS`.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        self.assertEqual(
            resolve_effect(eff, (StubResponse(202, {}), {"server": {}})),
            (StepResult.SUCCESS, []))

    def test_create_server_400_parseable_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in 400 failure code,
        returns with :obj:`StepResult.FAILURE` and whatever message was
        included in the Nova bad request message.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        # 400's we've seen so far
        nova_400s = (
            ("Bad networks format: network uuid is not in proper format "
             "(2b55377-890e-4fc9-9ece-ad5a414a788e)"),
            "Image 644d0755-e69b-4ca0-b99b-3abc2f20f7c0 is not active.",
            "Flavor's disk is too small for requested image.",
            "Invalid key_name provided.",
            ("Requested image 1dff348d-c06e-4567-a0b2-f4342575979e has "
             "automatic disk resize disabled."),
            "OS-DCF:diskConfig must be either 'MANUAL' or 'AUTO'.",
        )
        for message in nova_400s:
            api_error = APIError(
                code=400,
                body=json.dumps({
                    'badRequest': {
                        'message': message,
                        'code': 400
                    }
                }),
                headers={})
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(api_error),
                               is_error=True),
                (StepResult.FAILURE, [message]))

    def test_create_server_400_unrecognized_failures_retry(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a 400 failure code
        without a recognized body, invalidates the auth cache and returns with
        :obj:`StepResult.RETRY`.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        # 400's with we don't recognize
        invalid_400s = (
            json.dumps({
                "what?": {
                    "message": "Invalid key_name provided.", "code": 400
                }}),
            json.dumps(["not expected json format"]),
            "not json")

        for message in invalid_400s:
            api_error = APIError(code=400, body=message, headers={})
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(api_error),
                               is_error=True),
                (StepResult.RETRY, []))

    def test_create_server_403_json_parseable_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a 403 failure code
        with a recognized JSON body, returns with :obj:`StepResult.FAILURE` and
        whatever message was included in the Nova forbidden message.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        # 403's with JSON bodies we've seen so far that are not auth issues
        nova_json_403s = (
            ("Quota exceeded for ram: Requested 1024, but already used 131072 "
             "of 131072 ram"),
            ("Quota exceeded for instances: Requested 1, but already used "
             "100 of 100 instances"),
            ("Quota exceeded for onmetal-compute-v1-instances: Requested 1, "
             "but already used 10 of 10 onmetal-compute-v1-instances")
        )

        for message in nova_json_403s:
            api_error = APIError(
                code=403,
                body=json.dumps({
                    "forbidden": {
                        "message": message,
                        "code": 403
                    }
                }),
                headers={})
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(api_error),
                               is_error=True),
                (StepResult.FAILURE, [message]))

    def test_create_server_403_plaintext_parseable_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a 403 failure code
        with a recognized plain text body, returns with
        :obj:`StepResult.FAILURE` and whatever message was included in the
        Nova forbidden message.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        # 403's with JSON bodies we've seen so far that are not auth issues
        nova_plain_403s = (
            ("Networks (00000000-0000-0000-0000-000000000000,"
             "11111111-1111-1111-1111-111111111111) required but missing"),
            "Networks (00000000-0000-0000-0000-000000000000) not allowed",
            "Exactly 1 isolated network(s) must be attached"
        )

        for message in nova_plain_403s:
            api_error = APIError(
                code=403,
                body="".join((
                    "403 Forbidden\n\n",
                    "Access was denied to this resource.\n\n ",
                    message)),
                headers={})
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(api_error),
                               is_error=True),
                (StepResult.FAILURE, [message]))

    def test_create_server_403_unrecognized_failures_retry(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a 403 failure code
        without a recognized body, invalidates the auth cache and returns with
        :obj:`StepResult.RETRY`.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        # 403's with JSON and plaintext bodies don't recognize
        invalid_403s = (
            json.dumps({"what?": {"message": "meh", "code": 403}}),
            "403 Forbidden\n\nAccess was denied to this resource.\n\n bleh",
            ("403 Forbidden\n\nAccess was denied to this resource.\n\n "
             "Quota exceeded for ram: Requested 1024, but already used 131072 "
             "of 131072 ram"),
            "not even a message")

        for message in invalid_403s:
            api_error = APIError(code=403, body=message, headers={})
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(api_error),
                               is_error=True),
                (StepResult.RETRY, []))

    def test_create_server_non_400_or_403_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a non-400, non-403
        failure code without a recognized body, invalidates the auth cache and
        returns with :obj:`StepResult.RETRY`.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        api_error = APIError(code=500, body="this is a 500", headers={})
        self.assertEqual(
            resolve_effect(eff, service_request_error_response(api_error),
                           is_error=True),
            (StepResult.RETRY, []))


class StepAsEffectTests(SynchronousTestCase):
    """
    Tests for converting :obj:`IStep` implementations to :obj:`Effect`s.
    """
    def test_delete_server(self):
        """
        :obj:`DeleteServer.as_effect` produces a request for deleting a server.
        """
        delete = DeleteServer(server_id='abc123')
        eff = delete.as_effect()
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'DELETE',
                'servers/abc123',
                success_pred=has_code(204, 404)).intent)

        self.assertEqual(
            resolve_effect(eff, (None, {})),
            (StepResult.SUCCESS, []))

        self.assertEqual(
            resolve_effect(eff,
                           (APIError, APIError(500, None, None), None),
                           is_error=True),
            (StepResult.RETRY, []))

    def test_set_metadata_item(self):
        """
        :obj:`SetMetadataItemOnServer.as_effect` produces a request for
        setting a metadata item on a particular server.
        """
        meta = SetMetadataItemOnServer(server_id='abc123', key='metadata_key',
                                       value='teapot')
        eff = meta.as_effect()
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'PUT',
                'servers/abc123/metadata/metadata_key',
                data={'meta': {'metadata_key': 'teapot'}},
                success_pred=has_code(200, 404)).intent)

        self.assertEqual(
            resolve_effect(eff, (None, {})),
            (StepResult.SUCCESS, []))

        self.assertEqual(
            resolve_effect(eff,
                           (APIError, APIError(500, None, None), None),
                           is_error=True),
            (StepResult.RETRY, []))

    def test_change_load_balancer_node(self):
        """
        :obj:`ChangeCLBNode.as_effect` produces a request for
        modifying a load balancer node.
        """
        changenode = ChangeCLBNode(
            lb_id='abc123',
            node_id='node1',
            condition='DRAINING',
            weight=50,
            type="PRIMARY")
        self.assertEqual(
            changenode.as_effect(),
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'PUT',
                'loadbalancers/abc123/nodes/node1',
                data={'condition': 'DRAINING',
                      'weight': 50},
                success_pred=has_code(202)))

    def test_add_nodes_to_clb(self):
        """
        :obj:`AddNodesToCLB` produces a request for adding any number of nodes
        to a cloud load balancer.
        """
        lb_id = "12345"
        lb_nodes = pset([
            ('1.2.3.4', CLBDescription(lb_id=lb_id, port=80)),
            ('1.2.3.4', CLBDescription(lb_id=lb_id, port=8080)),
            ('2.3.4.5', CLBDescription(lb_id=lb_id, port=80))
        ])
        step = AddNodesToCLB(lb_id=lb_id, address_configs=lb_nodes)
        request = step.as_effect()

        self.assertEqual(
            request.intent,
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'POST',
                "loadbalancers/12345/nodes",
                json_response=True,
                success_pred=ANY,
                data={"nodes": ANY}).intent)

        node_data = sorted(request.intent.data['nodes'],
                           key=lambda n: (n['address'], n['port']))
        self.assertEqual(node_data, [
            {'address': '1.2.3.4',
             'port': 80,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1},
            {'address': '1.2.3.4',
             'port': 8080,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1},
            {'address': '2.3.4.5',
             'port': 80,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1}
        ])

        self.assertEqual(
            resolve_effect(request, (None, {})),
            (StepResult.SUCCESS, []))

        self.assertEqual(
            resolve_effect(request,
                           (APIError, APIError(500, None, None), None),
                           is_error=True),
            (StepResult.FAILURE, []))

    def test_add_nodes_to_clb_predicate(self):
        """
        :obj:`AddNodesToCLB` only accepts 202, 413, and some 422 responses.
        """
        lb_id = "12345"
        lb_nodes = pset([('1.2.3.4', CLBDescription(lb_id=lb_id, port=80))])
        step = AddNodesToCLB(lb_id=lb_id, address_configs=lb_nodes)
        request = step.as_effect()

        self.assertTrue(request.intent.json_response)

        predicate = request.intent.success_pred

        self.assertEqual(
            resolve_effect(request,
                           (APIError, APIError(422, None, None), None),
                           is_error=True),
            (StepResult.FAILURE, []))

        self.assertTrue(predicate(StubResponse(202, {}), None))
        self.assertTrue(predicate(StubResponse(413, {}), None))
        self.assertTrue(predicate(
            StubResponse(422, {}),
            {
                "message": "Duplicate nodes detected. One or more "
                           "nodes already configured on load "
                           "balancer.",
                "code": 422
            }))
        self.assertTrue(predicate(
            StubResponse(422, {}),
            {
                "message": "Load Balancer '12345' has a status of "
                           "'PENDING_UPDATE' and is considered immutable.",
                "code": 422
            }))

        self.assertFalse(predicate(StubResponse(404, {}), None))
        self.assertFalse(predicate(
            StubResponse(422, {}),
            {
                "message": "The load balancer is deleted and considered "
                           "immutable.",
                "code": 422
            }))
        self.assertFalse(predicate(
            StubResponse(422, {}),
            {
                "message": "Load Balancer '{0}' has a status of "
                           "'PENDING_DELETE' and is considered immutable."
                           .format(lb_id),
                "code": 422
            }))

    def test_add_nodes_to_clb_422_success_and_failures(self):
        """
        :obj:`AddNodesToCLB` returns SUCCESS on recognized 422 failures, and
        FAILURE on unrecognized 422 failures.
        """
        lb_id = "12345"
        lb_nodes = pset([('1.2.3.4', CLBDescription(lb_id=lb_id, port=80))])
        step = AddNodesToCLB(lb_id=lb_id, address_configs=lb_nodes)
        eff = step.as_effect()

        bad_response = ("Load Balancer '12345' has a status of "
                        "'PENDING_DELETE' and is considered immutable.")
        good_response = ("Load Balancer '12345' has a status of "
                         "'PENDING_UPDATE' and is considered immutable.")

        self.assertEqual(
            sync_perform(
                EQDispatcher([(
                    eff.intent,
                    (StubResponse(422, {}),
                     {'message': good_response, 'code': 422})
                )]),
                eff),
            (StepResult.SUCCESS, []))

        self.assertEqual(
            sync_perform(
                EQDispatcher([(
                    eff.intent,
                    (StubResponse(422, {}),
                     {'message': bad_response, 'code': 422})
                )]),
                eff),
            (StepResult.FAILURE, []))

    def test_remove_nodes_from_clb(self):
        """
        :obj:`RemoveNodesToCLB` produces a request for deleting any number of
        nodes from a cloud load balancer.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]

        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=node_ids)
        request = step.as_effect()
        self.assertEqual(
            request.intent,
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'DELETE',
                "loadbalancers/12345/nodes",
                params={'id': list(node_ids)},
                json_response=True,
                success_pred=ANY).intent)

    def test_remove_nodes_from_clb_predicate(self):
        """
        :obj:`RemoveNodesFromCLB` only accepts 202, 413, 400, and some 422
        responses.  However, only 202, 413, and 422s are covered by this test.
        400's will be covered by another test as they require retry.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]
        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=node_ids)
        request = step.as_effect()

        self.assertTrue(request.intent.json_response)

        predicate = request.intent.success_pred

        self.assertTrue(predicate(StubResponse(202, {}), None))
        self.assertTrue(predicate(StubResponse(413, {}), None))
        self.assertTrue(predicate(
            StubResponse(422, {}),
            {
                "message": "The load balancer is deleted and considered "
                           "immutable.",
                "code": 422
            }))
        self.assertTrue(predicate(
            StubResponse(422, {}),
            {
                "message": "Load Balancer '12345' has a status of "
                           "'PENDING_UPDATE' and is considered immutable.",
                "code": 422
            }))
        self.assertTrue(predicate(
            StubResponse(422, {}),
            {
                "message": "Load Balancer '12345' has a status of "
                           "'PENDING_DELETE' and is considered immutable.",
                "code": 422
            }))

        self.assertFalse(predicate(StubResponse(404, {}), None))
        self.assertFalse(predicate(
            StubResponse(422, {}),
            {
                "message": "Duplicate nodes detected. One or more "
                           "nodes already configured on load "
                           "balancer.",
                "code": 422
            }))
        # This one is just malformed but similar to a good message.
        self.assertFalse(predicate(
            StubResponse(422, {}),
            {
                "message": "The load balancer is considered immutable.",
                "code": 422
            }))

    def test_remove_nodes_from_clb_retry(self):
        """
        :obj:`RemoveNodesFromCLB`, on receiving a 400, parses out the nodes
        that are no longer on the load balancer, and retries the bulk delete
        with those nodes removed.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]
        error_body = {
            "validationErrors": {
                "messages": [
                    "Node ids 1,2,3 are not a part of your loadbalancer"
                ]
            },
            "message": "Validation Failure",
            "code": 400,
            "details": "The object is not valid"
        }

        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=node_ids)
        eff = resolve_effect(step.as_effect(),
                             (StubResponse(400, {}), error_body))
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'DELETE',
                'loadbalancers/12345/nodes',
                params={'id': ['0', '4']},
                success_pred=ANY,
                json_response=True).intent)

    def _generic_bulk_rcv3_step_test(self, step_class, expected_method):
        """
        A generic test for bulk RCv3 steps.

        :param step_class: The step class under test.
        :param str method: The expected HTTP method of the request.
        """
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
        step = step_class(lb_node_pairs=lb_node_pairs)
        request = step.as_effect()
        self.assertEqual(request.intent.service_type,
                         ServiceType.RACKCONNECT_V3)
        self.assertEqual(request.intent.method, expected_method)

        success_pred = request.intent.success_pred
        if request.intent.method == "POST":
            self.assertEqual(success_pred, has_code(201, 409))
        else:
            self.assertEqual(success_pred, has_code(204, 409))

        self.assertEqual(request.intent.url, "load_balancer_pools/nodes")
        self.assertEqual(request.intent.headers, None)

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

        def key_fn(e):
            return (e["load_balancer_pool"]["id"], e["cloud_server"]["id"])

        request_data = sorted(request.intent.data, key=key_fn)
        self.assertEqual(request_data, expected_data)

    def test_add_nodes_to_rcv3_load_balancers(self):
        """
        :obj:`BulkAddToRCv3.as_effect` produces a request for
        adding any combination of nodes to any combination of RCv3 load
        balancers.
        """
        self._generic_bulk_rcv3_step_test(BulkAddToRCv3, "POST")

    def test_remove_nodes_from_rcv3_load_balancers(self):
        """
        :obj:`BulkRemoveFromRCv3.as_effect` produces a request
        for removing any combination of nodes from any combination of RCv3
        load balancers.
        """
        self._generic_bulk_rcv3_step_test(
            BulkRemoveFromRCv3, "DELETE")


_RCV3_TEST_DATA = {
    _RCV3_NODE_NOT_A_MEMBER_PATTERN: [
        ('Node d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is not a member of '
         'Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2',
         {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
          'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
        ('Node D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is not a member of '
         'Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
         {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
          'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
    ],
    _RCV3_NODE_ALREADY_A_MEMBER_PATTERN: [
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
    _RCV3_LB_INACTIVE_PATTERN: [
        ('Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 is '
         'not in an ACTIVE state',
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ('Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2 is '
         'not in an ACTIVE state',
         {"lb_id": "D95AE0C4-6AB8-4873-B82F-F8433840CFF2"})
    ],
    _RCV3_LB_DOESNT_EXIST_PATTERN: [
        ("Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 does "
         "not exist",
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ("Load Balancer Pool D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 does "
         "not exist",
         {"lb_id": "D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2"})
    ]
}


class RCv3RegexTests(SynchronousTestCase):
    """
    Tests for the RCv3 error parsing regexes.
    """
    def _regex_test(self, test_pattern):
        """A generic regex test.

        Asserts that the given test pattern has test data, matches all
        of its test data, and that it does not match all of the test
        data for all of the other patterns.
        """
        self.assertIn(test_pattern, _RCV3_TEST_DATA)
        for pattern, test_data in _RCV3_TEST_DATA.iteritems():
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
        self._regex_test(_RCV3_NODE_NOT_A_MEMBER_PATTERN)

    def test_node_already_a_member_regex(self):
        """
        The regex for parsing messages saying the node is already part of
        the load balancer parses those messages. It rejects other
        messages.
        """
        self._regex_test(_RCV3_NODE_ALREADY_A_MEMBER_PATTERN)

    def test_lb_inactive_regex(self):
        """
        The regex for parsing messages saying the load balancer is
        inactive parses those messages. It rejects other messages.
        """
        self._regex_test(_RCV3_LB_INACTIVE_PATTERN)

    def test_no_such_lb_message(self):
        """
        The regex for parsing messages saying the load balancer doesn't
        exist, parses those messages. It rejects other messages.
        """
        self._regex_test(_RCV3_LB_DOESNT_EXIST_PATTERN)


class RCv3CheckBulkAddTests(SynchronousTestCase):
    """
    Tests for :func:`_rcv3_check_bulk_add`.
    """
    def test_good_response(self):
        """
        If the response code indicates success, the response was successful.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]

        resp = StubResponse(201, {})
        body = [{"cloud_server": {"id": node_id},
                 "load_balancer_pool": {"id": lb_id}}
                for (lb_id, node_id) in pairs]
        res = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(res, (StepResult.SUCCESS, []))

    def test_try_again(self):
        """
        If a node is already on the load balancer, returns an effect that
        removes the remaining load balancer pairs.
        """
        # This little piggy is already on the load balancer
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        # This little piggy is going to be added to this load balancer
        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        resp = StubResponse(409, {})
        body = {"errors":
                ["Cloud Server {node_id} is already a member of Load "
                 "Balancer Pool {lb_id}"
                 .format(node_id=node_a_id, lb_id=lb_a_id)]}
        eff = _rcv3_check_bulk_add(
            [(lb_a_id, node_a_id),
             (lb_b_id, node_b_id)],
            (resp, body))
        expected_intent = service_request(
            service_type=ServiceType.RACKCONNECT_V3,
            method="POST",
            url='load_balancer_pools/nodes',
            data=[
                {'load_balancer_pool': {'id': lb_b_id},
                 'cloud_server': {'id': node_b_id}}],
            success_pred=has_code(201, 409)).intent
        self.assertEqual(eff.intent, expected_intent)
        (partial_check_bulk_add, _), = eff.callbacks
        self.assertEqual(partial_check_bulk_add.func,
                         _rcv3_check_bulk_add)
        expected_pairs = pset([(lb_b_id, node_b_id)])
        self.assertEqual(partial_check_bulk_add.args, (expected_pairs,))
        self.assertEqual(partial_check_bulk_add.keywords, None)

    def test_node_already_a_member(self):
        """
        If all nodes were already member of the load balancers we were
        trying to add them to, the request is successful.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Cloud Server {node_id} is already a member of Load "
            "Balancer Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_lb_inactive(self):
        """
        If one of the LBs we tried to attach one or more nodes to is
        inactive, the request fails.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} is not in an ACTIVE state"
            .format(lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} was inactive".format(lb_id=lb_id)]))

    def test_multiple_lbs_inactive(self):
        """
        If multiple LBs we tried to attach one or more nodes to is
        inactive, the request fails, and all of the inactive LBs are
        reported.

        By logging as much of the failure as we can see, we will
        hopefully produce better audit logs.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_1_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        lb_2_id = 'fb32470f-6ebe-44a9-9360-3f48c9ac768c'
        pairs = [(lb_1_id, node_id), (lb_2_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} is not in an ACTIVE state"
            .format(lb_id=lb_id) for lb_id in [lb_1_id, lb_2_id]]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} was inactive".format(lb_id=lb_id)
              for lb_id in [lb_1_id, lb_2_id]]))

    def test_lb_does_not_exist(self):
        """
        If one of the LBs we tried to attach one or more nodes to does not
        exist, the request fails.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} does not exist"
            .format(lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} does not exist".format(lb_id=lb_id)]))

    def test_multiple_lbs_do_not_exist(self):
        """
        If multiple LBs we tried to attach one or more nodes to do not
        exist, the request fails, and all of the nonexistent LBs are
        reported.

        By logging as much of the failure as we can see, we will
        hopefully produce better audit logs.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_1_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        lb_2_id = 'fb32470f-6ebe-44a9-9360-3f48c9ac768c'
        pairs = [(lb_1_id, node_id), (lb_2_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} does not exist"
            .format(lb_id=lb_id) for lb_id in [lb_1_id, lb_2_id]]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} does not exist".format(lb_id=lb_id)
              for lb_id in [lb_1_id, lb_2_id]]))


class RCv3CheckBulkDeleteTests(SynchronousTestCase):
    """
    Tests for :func:`_rcv3_check_bulk_delete`.
    """
    def test_good_response(self):
        """
        If the response code indicates success, the response was successful.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]

        resp = StubResponse(204, {})
        body = [{"cloud_server": {"id": node_id},
                 "load_balancer_pool": {"id": lb_id}}
                for (lb_id, node_id) in pairs]
        res = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(res, (StepResult.SUCCESS, []))

    def test_try_again(self):
        """
        If a node was already removed (or maybe was never part of the load
        balancer pool to begin with), or some load balancer was
        inactive, or one of the load balancers doesn't exist, returns
        an effect that removes the remaining load balancer pairs.
        """
        # This little piggy isn't even on this load balancer.
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        # This little piggy is going to be removed from this load balancer.
        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        # This little piggy isn't active!
        node_c_id = '08944038-80ba-4ae1-a188-c827444e02e2'
        lb_c_id = '150895a5-1aa7-45b7-b7a4-98b9c282f800'

        # This isn't even a little piggy!
        node_d_id = 'bc1e94c3-0c88-4828-9e93-d42259280987'
        lb_d_id = 'de52879e-1f84-4ecd-8988-91dfdc99570d'

        resp = StubResponse(409, {})
        body = {"errors":
                ["Node {node_id} is not a member of Load Balancer "
                 "Pool {lb_id}".format(node_id=node_a_id, lb_id=lb_a_id),
                 "Load Balancer Pool {lb_id} is not in an ACTIVE state"
                 .format(lb_id=lb_c_id),
                 "Load Balancer Pool {lb_id} does not exist"
                 .format(lb_id=lb_d_id)]}
        eff = _rcv3_check_bulk_delete(
            [(lb_a_id, node_a_id),
             (lb_b_id, node_b_id),
             (lb_c_id, node_c_id),
             (lb_d_id, node_d_id)],
            (resp, body))
        expected_intent = service_request(
            service_type=ServiceType.RACKCONNECT_V3,
            method="DELETE",
            url='load_balancer_pools/nodes',
            data=[
                {'load_balancer_pool': {'id': lb_b_id},
                 'cloud_server': {'id': node_b_id}}],
            success_pred=has_code(204, 409)).intent
        self.assertEqual(eff.intent, expected_intent)
        (partial_check_bulk_delete, _), = eff.callbacks
        self.assertEqual(partial_check_bulk_delete.func,
                         _rcv3_check_bulk_delete)
        expected_pairs = pset([(lb_b_id, node_b_id)])
        self.assertEqual(partial_check_bulk_delete.args, (expected_pairs,))
        self.assertEqual(partial_check_bulk_delete.keywords, None)

    def test_nothing_to_retry(self):
        """
        If there are no further pairs to try and remove, the request was
        successful.

        This is similar to other tests, except that it tests the
        combination of all of them, even if there are several (load
        balancer, node) pairs for each reason.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        node_c_id = '08944038-80ba-4ae1-a188-c827444e02e2'
        lb_c_id = '150895a5-1aa7-45b7-b7a4-98b9c282f800'

        node_d_id = 'bc1e94c3-0c88-4828-9e93-d42259280987'
        lb_d_id = 'de52879e-1f84-4ecd-8988-91dfdc99570d'

        not_a_member_pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]
        inactive_pairs = [(lb_c_id, node_c_id)]
        nonexistent_lb_pairs = [(lb_d_id, node_d_id)]
        all_pairs = not_a_member_pairs + inactive_pairs + nonexistent_lb_pairs

        resp = StubResponse(409, {})
        body = {"errors":
                ["Node {node_id} is not a member of Load Balancer "
                 "Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)
                 for (lb_id, node_id) in not_a_member_pairs] +
                ["Load Balancer Pool {} is not in an ACTIVE state"
                 .format(lb_id) for (lb_id, _node_id)
                 in inactive_pairs] +
                ["Load Balancer Pool {} does not exist"
                 .format(lb_id) for (lb_id, _node_id)
                 in nonexistent_lb_pairs]}
        result = _rcv3_check_bulk_delete(all_pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_inactive_lb(self):
        """
        If the load balancer pool is inactive, the response was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        inactive_lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(inactive_lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": ["Load Balancer Pool {} is not in an ACTIVE state"
                           .format(inactive_lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_lb_does_not_exist(self):
        """
        If the load balancer doesn't even exist, the delete was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        nonexistent_lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        pairs = [(nonexistent_lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": ["Load Balancer Pool {} does not exist"
                           .format(nonexistent_lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_node_not_a_member(self):
        """
        If the nodes are already not member of the load balancer pools
        they're being removed from, the response was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Node {node_id} is not a member of Load Balancer "
            "Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))
