"""
Tests for :mod:`otter.worker_intents`
"""

from functools import partial

from effect import Effect, TypeDispatcher
from effect import sync_perform

from twisted.trial.unittest import SynchronousTestCase

from otter.supervisor import set_supervisor
from otter.worker_intents import (
    EvictServerFromScalingGroup, perform_evict_server)
from otter.test.utils import FakeSupervisor, mock_group


class PerformEvictionTests(SynchronousTestCase):
    """
    Tests for :func:`perform_evict_server` function
    """
    def test_perform_eviction(self):
        """
        Call supervisor's scrub metadata function.
        """
        supervisor = FakeSupervisor()
        set_supervisor(supervisor)
        self.addCleanup(set_supervisor, None)

        log, group = (object(), mock_group(None))
        intent = EvictServerFromScalingGroup(
            log=log, transaction_id='transaction_id',
            scaling_group=group, server_id='server_id')

        r = sync_perform(
            TypeDispatcher({
                EvictServerFromScalingGroup: partial(
                    perform_evict_server, supervisor)
            }),
            Effect(intent))

        self.assertIsNone(r)
        self.assertEqual(
            supervisor.scrub_calls,
            [(log, "transaction_id", group.tenant_id, 'server_id')])
