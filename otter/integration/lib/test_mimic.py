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

    def test_sequenced_behaviors(self):
        """
        Cause a sequence of behaviors, and succeeds on 201.  When a test case
        is provided for which a cleanup should be added, delete is added as
        a cleanup.
        """
        class FakeTestCase(object):
            def addCleanup(test_self, *args, **kwargs):
                test_self.called_with = (args, kwargs)

        test_case = FakeTestCase()

        criteria = [{"server_name": "name_criteria_.*"}]
        behaviors = [{'name': "behavior name",
                      'parameters': {"behavior": "params"}}]

        _treq = get_fake_treq(
            self, 'POST', "mimicnovaurl/behaviors/some_event",
            ((json.dumps({'criteria': criteria,
                          'name': "sequence",
                          'parameters': {"behaviors": behaviors}}),),
             self.expected_kwargs),
            (Response(201), '{"id": "my_id"}'))

        mimic_nova = MimicNova(pool=self.pool, test_case=test_case, treq=_treq)
        d = mimic_nova.sequenced_behaviors(
            self.rcs, criteria, behaviors, event_description="some_event")
        self.assertEqual("my_id", self.successResultOf(d))
        self.assertEqual(
            test_case.called_with,
            ((mimic_nova.delete_behavior, self.rcs,
              "my_id", "some_event", [204]),
             {}))

    def test_delete_behavior(self):
        """
        Delete an existing behavior.
        """
        _treq = get_fake_treq(
            self, 'DELETE', "mimicnovaurl/behaviors/some_event/behavior_id",
            ((),
             self.expected_kwargs),
            (Response(204), "successfully deleted behavior"))

        d = MimicNova(pool=self.pool, treq=_treq).delete_behavior(
            self.rcs, "behavior_id", event_description="some_event")
        self.assertEqual('successfully deleted behavior',
                         self.successResultOf(d))
