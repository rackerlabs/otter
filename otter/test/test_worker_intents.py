"""
Tests for :mod:`otter.worker_intents`
"""

from functools import partial

from effect import Effect, TypeDispatcher
from effect import sync_perform

import mock

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from txeffect import deferred_performer

from otter.supervisor import set_supervisor
from otter.test.utils import FakeSupervisor, mock_group
from otter.worker_intents import (
    EvictServerFromScalingGroup, get_eviction_dispatcher, perform_evict_server)


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


class EvictionDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_eviction_dispatcher`."""

    @mock.patch('otter.worker_intents.perform_evict_server')
    def test_eviction_dispatcher(self, mock_performer):
        """The :obj:`EvictServerFromScalingGroup` performer is called."""

        @deferred_performer
        def performer(supervisor, d, i):
            return succeed(
                (supervisor,
                 i.log, i.transaction_id, i.scaling_group, i.server_id))

        mock_performer.side_effect = performer

        dispatcher = get_eviction_dispatcher('supervisor')
        intent = EvictServerFromScalingGroup(
            log='log', transaction_id='transaction_id',
            scaling_group='scaling_group', server_id='server_id')
        eff = Effect(intent)
        self.assertEqual(sync_perform(dispatcher, eff),
                         ('supervisor', 'log', 'transaction_id',
                          'scaling_group', 'server_id'))
