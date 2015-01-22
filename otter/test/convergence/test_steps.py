"""Tests for convergence steps."""

from pyrsistent import pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.steps import (
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    CreateServer,
    DeleteServer,
    RemoveFromCLB,
    SetMetadataItemOnServer)
from otter.http import has_code, service_request


class StepAsEffectTests(SynchronousTestCase):
    """
    Tests for converting :obj:`IStep` implementations to :obj:`Effect`s.
    """

    def test_create_server(self):
        """
        :obj:`CreateServer.as_effect` produces a request for creating a server.
        """
        create = CreateServer(
            launch_config=pmap({'name': 'myserver', 'flavorRef': '1'}))
        self.assertEqual(
            create.as_effect(),
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data=pmap({'name': 'myserver', 'flavorRef': '1'})))

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
        step = step_class(lb_node_pairs=pset([
            ("lb-1", "node-a"),
            ("lb-1", "node-b"),
            ("lb-1", "node-c"),
            ("lb-1", "node-d"),
            ("lb-2", "node-a"),
            ("lb-2", "node-b"),
            ("lb-3", "node-c"),
            ("lb-3", "node-d")
        ]))
        request = step.as_effect()
        self.assertEqual(request.intent.service_type,
                         ServiceType.RACKCONNECT_V3)
        self.assertEqual(request.intent.method, expected_method)
        expected_code = 201 if request.intent.method == "POST" else 204
        self.assertEqual(request.intent.success_pred, has_code(expected_code))
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
