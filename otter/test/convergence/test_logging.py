from effect import sync_perform
from effect.testing import SequenceDispatcher

from pyrsistent import pbag, pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.logging import log_steps
from otter.convergence.model import (
    CLBDescription, CLBNodeCondition, CLBNodeType)
from otter.convergence.steps import (
    AddNodesToCLB, ChangeCLBNode, CreateServer, DeleteServer,
    RemoveNodesFromCLB
)
from otter.log.intents import Log
from otter.test.utils import noop, test_dispatcher


def _clbd(lbid, port):
    return CLBDescription(lb_id=lbid, port=port)


class LogStepsTests(SynchronousTestCase):
    def assert_logs(self, steps, intents):
        sequence = SequenceDispatcher([(intent, noop) for intent in intents])
        with sequence.consume():
            sync_perform(test_dispatcher(sequence), log_steps(steps))

    def test_create_servers(self):
        cfg = {'configgy': 'configged'}
        creates = pbag([CreateServer(server_config=pmap(cfg))] * 3)
        self.assert_logs(creates, [
            Log('convergence-create-servers',
                fields={'num_servers': 3, 'server_config': cfg,
                        'cloud_feed': True})])

    def test_delete_servers(self):
        deletes = pbag([DeleteServer(server_id='1'),
                        DeleteServer(server_id='2'),
                        DeleteServer(server_id='3')])
        self.assert_logs(deletes, [
            Log('convergence-delete-servers',
                fields={'server_ids': ['1', '2', '3'],
                        'cloud_feed': True})
        ])

    def test_add_nodes_to_clbs(self):
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
            Log('convergence-add-nodes-to-clb',
                fields={'lb_id': 'lbid1',
                        'addresses': '10.0.0.1:1234, 10.0.0.2:1235',
                        'cloud_feed': True}),
            Log('convergence-add-nodes-to-clb',
                fields={'lb_id': 'lbid2',
                        'addresses': '10.0.0.1:4321',
                        'cloud_feed': True})
        ])

    def test_remove_nodes_from_clbs(self):
        removes = pbag([
            RemoveNodesFromCLB(lb_id='lbid1', node_ids=pset(['a', 'b', 'c'])),
            RemoveNodesFromCLB(lb_id='lbid2', node_ids=pset(['d', 'e', 'f']))
        ])

        self.assert_logs(removes, [
            Log('convergence-remove-nodes-from-clb',
                fields={'lb_id': 'lbid1',
                        'nodes': ['a', 'b', 'c'],
                        'cloud_feed': True}),
            Log('convergence-remove-nodes-from-clb',
                fields={'lb_id': 'lbid2',
                        'nodes': ['d', 'e', 'f'],
                        'cloud_feed': True}),
        ])

    def test_change_clb_node(self):
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
                    'lb_id': 'lbid1', 'nodes': 'node3',
                    'type': 'PRIMARY', 'condition': 'ENABLED', 'weight': 50,
                    'cloud_feed': True,
                }),
            Log('convergence-change-clb-nodes',
                fields={
                    'lb_id': 'lbid1', 'nodes': 'node1, node2',
                    'type': 'PRIMARY', 'condition': 'DRAINING', 'weight': 50,
                    'cloud_feed': True,
                }),
            Log('convergence-change-clb-nodes',
                fields={
                    'lb_id': 'lbid2', 'nodes': 'node4',
                    'type': 'PRIMARY', 'condition': 'ENABLED', 'weight': 50,
                    'cloud_feed': True,
                }),
        ])
