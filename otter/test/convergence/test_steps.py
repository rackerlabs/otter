"""Tests for convergence steps."""

from effect import Func
from effect.testing import resolve_effect

from pyrsistent import freeze, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.steps import (
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    CreateServer,
    DeleteServer,
    RemoveFromCLB,
    SetMetadataItemOnServer,
    _rcv3_check_bulk_delete,
    _RCV3_LB_INACTIVE_PATTERN,
    _RCV3_NODE_NOT_A_MEMBER_PATTERN)
from otter.http import has_code, service_request
from otter.test.utils import StubResponse
from otter.util.hashkey import generate_server_name


class StepAsEffectTests(SynchronousTestCase):
    """
    Tests for converting :obj:`IStep` implementations to :obj:`Effect`s.
    """

    def test_create_server(self):
        """
        :obj:`CreateServer.as_effect` produces a request for creating a server.
        """
        create = CreateServer(
            server_config=freeze({'server': {'name': 'myserver',
                                             'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'myserver-random-name',
                                 'flavorRef': '1'}}))

    def test_create_server_noname(self):
        """
        When no name is provided in the launch config, the name will be
        generated from scratch.
        """
        create = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'random-name', 'flavorRef': '1'}}))

    def test_delete_server(self):
        """
        :obj:`DeleteServer.as_effect` produces a request for deleting a server.
        """
        delete = DeleteServer(server_id='abc123')
        self.assertEqual(
            delete.as_effect(),
            service_request(
                ServiceType.CLOUD_SERVERS,
                'DELETE',
                'servers/abc123'))

    def test_set_metadata_item(self):
        """
        :obj:`SetMetadataItemOnServer.as_effect` produces a request for
        setting a metadata item on a particular server.
        """
        meta = SetMetadataItemOnServer(server_id='abc123', key='metadata_key',
                                       value='teapot')
        self.assertEqual(
            meta.as_effect(),
            service_request(
                ServiceType.CLOUD_SERVERS,
                'PUT',
                'servers/abc123/metadata/metadata_key',
                data={'meta': {'metadata_key': 'teapot'}}))

    def test_remove_from_load_balancer(self):
        """
        :obj:`RemoveFromCLB.as_effect` produces a request for
        removing a node from a load balancer.
        """
        lbremove = RemoveFromCLB(
            lb_id='abc123',
            node_id='node1')
        self.assertEqual(
            lbremove.as_effect(),
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'DELETE',
                'loadbalancers/abc123/node1'))

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
                      'weight': 50}))

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
            self.assertEqual(success_pred, has_code(201))
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
        key_fn = lambda e: (e["load_balancer_pool"]["id"],
                            e["cloud_server"]["id"])
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


class RCv3CheckBulkDeleteTests(SynchronousTestCase):
    """
    Tests for :func:`_rcv3_check_bulk_delete`.
    """
    def test_node_not_a_member_error_message_regex(self):
        """
        The regex for parsing messages saying the node isn't part of the
        load balancer parses those messages. It rejects other
        messages.
        """
        match = _RCV3_NODE_NOT_A_MEMBER_PATTERN.match

        test_data = [
            ('Node d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is not a member of '
             'Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2',
             {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
              'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
            ('Node D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is not a member of '
             'Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
             {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
              'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
        ]

        for message, expected_group_dict in test_data:
            res = match(message)
            self.assertNotIdentical(res, None)
            self.assertEqual(res.groupdict(), expected_group_dict)

        for message in ["Load Balancer Pool {lb_id} is not in an ACTIVE state"
                        .format(lb_id=lb_id) for lb_id in
                        ['d95ae0c4-6ab8-4873-b82f-f8433840cff2',
                         'D95AE0C4-6AB8-4873-B82F-F8433840CFF2']]:
            self.assertIdentical(match(message), None)

    def test_lb_inactive_regex(self):
        """
        The regex for parsing messages saying the load balancer is
        inactive parses those messages. It rejects other messages.
        """
        match = _RCV3_LB_INACTIVE_PATTERN.match

        test_data = [
            ('Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 is '
             'not in an ACTIVE state',
             ("d95ae0c4-6ab8-4873-b82f-f8433840cff2",)),
            ('Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2 is '
             'not in an ACTIVE state',
             ("D95AE0C4-6AB8-4873-B82F-F8433840CFF2",))
        ]

        for message, expected_groups in test_data:
            res = match(message)
            self.assertNotIdentical(res, None)
            self.assertEqual(res.groups(), expected_groups)

        for message in [
                'Node d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is not a member '
                'of Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2',
                'Node D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is not a member '
                'of Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2']:
            self.assertIdentical(match(message), None)

    def test_good_response(self):
        """
        If the response code indicates success, the response was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(node_id, lb_id)]

        resp = StubResponse(204, {})
        body = [{"cloud_server": {"id": node_id},
                 "load_balancer_pool": {"id": lb_id}}
                for (lb_id, node_id) in [("l1", "n1"),
                                         ("l2", "n2")]]
        res = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertIdentical(res, None)

    def test_try_again(self):
        """
        If a node was already removed (or maybe was never part of the load
        balancer pool to begin with), returns an effect that removes
        the remaining load balancer pairs.
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

        resp = StubResponse(409, {})
        body = {"errors":
                ["Node {node_id} is not a member of Load Balancer "
                 "Pool {lb_id}".format(node_id=node_a_id, lb_id=lb_a_id),
                 "Load Balancer Pool {lb_id} is not in an ACTIVE state"
                 .format(lb_id=lb_c_id)]}
        eff = _rcv3_check_bulk_delete(
            [(lb_a_id, node_a_id),
             (lb_b_id, node_b_id),
             (lb_c_id, node_c_id)],
            (resp, body))
        expected_eff = (
            service_request(
                service_type=ServiceType.RACKCONNECT_V3,
                method="DELETE",
                url='load_balancer_pools/nodes',
                data=[
                    {'load_balancer_pool': {'id': lb_b_id},
                     'cloud_server': {'id': node_b_id}}],
                success_pred=has_code(204, 409))
            .on(_rcv3_check_bulk_delete))
        self.assertEqual(eff, expected_eff)

    def test_bail_if_group_inactive(self):
        """
        If the load balancer pool is inactive, the response was unsuccessful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        inactive_lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(inactive_lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": ["Load Balancer Pool {} is not in an ACTIVE state"
                           .format(inactive_lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertIdentical(result, None)
