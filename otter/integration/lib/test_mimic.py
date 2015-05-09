"""Tests for :mod:`otter.integration.lib.nova`"""
import json

from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.mimic import MimicNova
from otter.integration.lib.test_nova import Response, get_fake_treq
from otter.util.http import headers


class MimicNovaTestCase(SynchronousTestCase):
    """
    Tests for :class:`Mimic`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()

        class FakeRCS(object):
            endpoints = {'mimic_nova': 'mimicnovaurl'}
            token = "token"

        self.rcs = FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {
            'headers': headers('token'),
            'pool': self.pool
        }

    def test_change_server_statuses(self):
        """
        Change server statuses calls the right endpoint and succeeds on 201.
        """
        _treq = get_fake_treq(
            self, 'POST', "mimicnovaurl/attributes",
            ((json.dumps({'status': {'id1': 'ERROR', 'id2': 'DELETED'}}),),
             self.expected_kwargs),
            (Response(201), "successful change response"))

        d = MimicNova(pool=self.pool, treq=_treq).change_server_statuses(
            self.rcs, {'id1': 'ERROR', 'id2': 'DELETED'})
        self.assertEqual('successful change response', self.successResultOf(d))
