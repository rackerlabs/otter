"""
Tests for logging in convergence (that steps are correctly logged).
"""

from effect import sync_perform
from effect.testing import SequenceDispatcher

from mock import ANY

from pyrsistent import freeze, pbag, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.logging import log_steps
from otter.convergence.model import (
    CLBDescription, CLBNodeCondition, CLBNodeType, ErrorReason)
from otter.convergence.steps import (
    AddNodesToCLB, BulkAddToRCv3, BulkRemoveFromRCv3, ChangeCLBNode,
    ConvergeLater, CreateServer, DeleteServer, RemoveNodesFromCLB,
    SetMetadataItemOnServer)
from otter.log.intents import Log
from otter.test.utils import noop, test_dispatcher


def _clbd(lbid, port):
    return CLBDescription(lb_id=lbid, port=port)


class LogStepsTests(SynchronousTestCase):
    """Tests for :func:`log_steps`."""

    def assert_logs(self, steps, intents):
        """Log some steps and ensure they result in the given Log intents."""
        sequence = SequenceDispatcher([(intent, noop) for intent in intents])
        with sequence.consume():
            sync_perform(test_dispatcher(sequence), log_steps(steps))

    def test_unhandled_steps(self):
        """
        Arbitrary unhandled steps return an effect that performs no logging.
        """
        steps = pbag([ConvergeLater([ErrorReason.String("foo")])])
        self.assert_logs(steps, [])

    def test_create_servers(self):
        """Logs :obj:`CreateServer`."""
        cfg = {'configgy': 'configged', 'nested': {'a': 'b'}}
        cfg2 = {'configgy': 'configged', 'nested': {'a': 'c'}}
        creates = pbag([
            CreateServer(server_config=freeze(cfg)),
            CreateServer(server_config=freeze(cfg)),
            CreateServer(server_config=freeze(cfg2))
            ])
        self.assert_logs(creates, [
            Log('convergence-create-servers',
                fields={'num_servers': 2, 'server_config': cfg,
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-create-servers',
                fields={'num_servers': 1, 'server_config': cfg2,
                        'cloud_feed': True, 'cloud_feed_id': ANY})
            ])

    def test_delete_servers(self):
        """Logs :obj:`DeleteServer`."""
        deletes = pbag([DeleteServer(server_id='1'),
                        DeleteServer(server_id='2'),
                        DeleteServer(server_id='3')])
        self.assert_logs(deletes, [
            Log('convergence-delete-servers',
                fields={'servers': ['1', '2', '3'], 'cloud_feed': True,
                        'cloud_feed_id': ANY})
        ])

    def test_add_nodes_to_clbs(self):
        """Logs :obj:`AddNodesToCLB`."""
        adds = pbag([
            AddNodesToCLB(
                lb_id='lbid1',
                address_configs=pset([('10.0.0.1', _clbd('lbid1', 1234))])),
            AddNodesToCLB(
                lb_id='lbid1',
                address_configs=pset([('10.0.0.2', _clbd('lbid1', 1235))])),
            AddNodesToCLB(
                lb_id='lbid2',
                address_configs=pset([('10.0.0.1', _clbd('lbid2', 4321))]))])
        self.assert_logs(adds, [
            Log('convergence-add-clb-nodes',
                fields={'lb_id': 'lbid1',
                        'addresses': ['10.0.0.1:1234', '10.0.0.2:1235'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-add-clb-nodes',
                fields={'lb_id': 'lbid2',
                        'addresses': ['10.0.0.1:4321'],
                        'cloud_feed': True, 'cloud_feed_id': ANY})
        ])

    def test_remove_nodes_from_clbs(self):
        """Logs :obj:`RemoveNodesFromCLB`."""
        removes = pbag([
            RemoveNodesFromCLB(lb_id='lbid1', node_ids=pset(['a', 'b', 'c'])),
            RemoveNodesFromCLB(lb_id='lbid2', node_ids=pset(['d', 'e', 'f']))
        ])

        self.assert_logs(removes, [
            Log('convergence-remove-clb-nodes',
                fields={'lb_id': 'lbid1',
                        'nodes': ['a', 'b', 'c'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-remove-clb-nodes',
                fields={'lb_id': 'lbid2',
                        'nodes': ['d', 'e', 'f'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
        ])

    def test_change_clb_node(self):
        """Logs :obj:`ChangeCLBNode`."""
        changes = pbag([
            ChangeCLBNode(lb_id='lbid1', node_id='node1',
                          condition=CLBNodeCondition.DRAINING,
                          type=CLBNodeType.PRIMARY,
                          weight=50),
            ChangeCLBNode(lb_id='lbid1', node_id='node2',
                          condition=CLBNodeCondition.DRAINING,
                          type=CLBNodeType.PRIMARY,
                          weight=50),
            ChangeCLBNode(lb_id='lbid1', node_id='node3',
                          condition=CLBNodeCondition.ENABLED,
                          type=CLBNodeType.PRIMARY,
                          weight=50),
            ChangeCLBNode(lb_id='lbid2', node_id='node4',
                          condition=CLBNodeCondition.ENABLED,
                          type=CLBNodeType.PRIMARY,
                          weight=50),
        ])
        self.assert_logs(changes, [
            Log('convergence-change-clb-nodes',
                fields={
                    'lb_id': 'lbid1', 'nodes': ['node3'],
                    'type': 'PRIMARY', 'condition': 'ENABLED', 'weight': 50,
                    'cloud_feed': True, 'cloud_feed_id': ANY
                }),
            Log('convergence-change-clb-nodes',
                fields={
                    'lb_id': 'lbid1', 'nodes': ['node1', 'node2'],
                    'type': 'PRIMARY', 'condition': 'DRAINING', 'weight': 50,
                    'cloud_feed': True, 'cloud_feed_id': ANY
                }),
            Log('convergence-change-clb-nodes',
                fields={
                    'lb_id': 'lbid2', 'nodes': ['node4'],
                    'type': 'PRIMARY', 'condition': 'ENABLED', 'weight': 50,
                    'cloud_feed': True, 'cloud_feed_id': ANY
                }),
        ])

    def test_bulk_add_to_rcv3(self):
        """Logs :obj:`BulkAddToRCv3`."""
        adds = pbag([
            BulkAddToRCv3(lb_node_pairs=pset([
                ('lb1', 'node1'), ('lb1', 'node2'),
                ('lb2', 'node2'), ('lb2', 'node3'),
                ('lb3', 'node4')])),
            BulkAddToRCv3(lb_node_pairs=pset([
                ('lba', 'nodea'), ('lba', 'nodeb'),
                ('lb1', 'nodea')]))
        ])
        self.assert_logs(adds, [
            Log('convergence-add-rcv3-nodes',
                fields={'lb_id': 'lb1', 'servers': ['node1', 'node2', 'nodea'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-add-rcv3-nodes',
                fields={'lb_id': 'lb2', 'servers': ['node2', 'node3'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-add-rcv3-nodes',
                fields={'lb_id': 'lb3', 'servers': ['node4'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-add-rcv3-nodes',
                fields={'lb_id': 'lba', 'servers': ['nodea', 'nodeb'],
                        'cloud_feed': True, 'cloud_feed_id': ANY})
        ])

    def test_bulk_remove_from_rcv3(self):
        """Logs :obj:`BulkRemoveFromRCv3`."""
        adds = pbag([
            BulkRemoveFromRCv3(lb_node_pairs=pset([
                ('lb1', 'node1'), ('lb1', 'node2'),
                ('lb2', 'node2'), ('lb2', 'node3'),
                ('lb3', 'node4')])),
            BulkRemoveFromRCv3(lb_node_pairs=pset([
                ('lba', 'nodea'), ('lba', 'nodeb'),
                ('lb1', 'nodea')]))
        ])
        self.assert_logs(adds, [
            Log('convergence-remove-rcv3-nodes',
                fields={'lb_id': 'lb1', 'servers': ['node1', 'node2', 'nodea'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-remove-rcv3-nodes',
                fields={'lb_id': 'lb2', 'servers': ['node2', 'node3'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-remove-rcv3-nodes',
                fields={'lb_id': 'lb3', 'servers': ['node4'],
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-remove-rcv3-nodes',
                fields={'lb_id': 'lba', 'servers': ['nodea', 'nodeb'],
                        'cloud_feed': True, 'cloud_feed_id': ANY})
        ])

    def test_set_metadata_item_on_server(self):
        """Logs :obj:`SetMetadataItemOnServer`."""
        sets = pbag([
            SetMetadataItemOnServer(server_id='s1', key='k1', value='v1'),
            SetMetadataItemOnServer(server_id='s2', key='k1', value='v1'),
            SetMetadataItemOnServer(server_id='s3', key='k2', value='v2'),
        ])

        self.assert_logs(sets, [
            Log('convergence-set-server-metadata',
                fields={'servers': ['s1', 's2'], 'key': 'k1', 'value': 'v1',
                        'cloud_feed': True, 'cloud_feed_id': ANY}),
            Log('convergence-set-server-metadata',
                fields={'servers': ['s3'], 'key': 'k2', 'value': 'v2',
                        'cloud_feed': True, 'cloud_feed_id': ANY})
        ])
