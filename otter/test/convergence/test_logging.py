from effect import sync_perform
from effect.testing import SequenceDispatcher

from pyrsistent import pbag, pmap, pset

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.logging import log_steps
from otter.convergence.model import CLBDescription
from otter.convergence.steps import (
    AddNodesToCLB, CreateServer, DeleteServer
)
from otter.log.intents import Log, LogErr
from otter.test.utils import noop, test_dispatcher


def _clbd(lbid, port):
    return CLBDescription(lb_id=lbid, port=port)

class LogStepsTests(SynchronousTestCase):
    def assert_logs(self, eff, intents):
        sequence = SequenceDispatcher([(intent, noop) for intent in intents])
        with sequence.consume():
            sync_perform(test_dispatcher(sequence), eff)

    def test_create_servers(self):
        cfg = {'configgy': 'configged'}
        creates = pbag([CreateServer(server_config=pmap(cfg))] * 3)
        eff = log_steps(creates)
        self.assert_logs(eff, [
            Log('convergence-create-servers',
                fields={'num_servers': 3, 'server_config': cfg,
                        'cloud_feed': True})])

    def test_delete_servers(self):
        deletes = pbag([DeleteServer(server_id='1'),
                        DeleteServer(server_id='2'),
                        DeleteServer(server_id='3')])
        eff = log_steps(deletes)
        self.assert_logs(eff, [
            Log('convergence-delete-servers',
                fields={'server_ids': ['1', '2', '3'],
                'cloud_feed': True})
        ])

    def test_add_nodes_to_clbs(self):
        adds = pbag([
            AddNodesToCLB(
                lb_id='lbid1',
                address_configs=pset([('10.0.0.1', _clbd('lbid1', 1234))]),
                ),
            AddNodesToCLB(
                lb_id='lbid1',
                address_configs=pset([('10.0.0.2', _clbd('lbid1', 1235))]),
                ),
            AddNodesToCLB(
                lb_id='lbid2',
                address_configs=pset([('10.0.0.1', _clbd('lbid2', 4321))]),
                )])
        self.assert_logs(log_steps(adds), [
            Log('convergence-add-nodes-to-clb',
                fields={'lb_id': 'lbid1',
                        'addresses': '10.0.0.1:1234, 10.0.0.2:1235',
                        'cloud_feed': True}),
            Log('convergence-add-nodes-to-clb',
                fields={'lb_id': 'lbid2',
                        'addresses': '10.0.0.1:4321',
                        'cloud_feed': True})
        ])
