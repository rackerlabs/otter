"""Tests for :mod:`otter.integration.lib.nova`"""
import json

import mock

from treq.testing import RequestSequence, StringStubbingResource, StubTreq

from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.mimic import MimicCLB, MimicIdentity, MimicNova
from otter.integration.lib.test_nova import Response, get_fake_treq


def _get_fake_test_case(expected_old_treq, expected_new_treq):
    class FakeTestCase(object):
        def addCleanup(test_self, *args, **kwargs):
            test_self.add_cleanup_called_with = (list(args), kwargs)

        def cleanup(test_self):
            args, kwargs = test_self.add_cleanup_called_with
            for i in range(1, len(args)):
                if args[i] == expected_old_treq:
                    args[i] = expected_new_treq
            for k in kwargs:
                if kwargs[k] == expected_old_treq:
                    kwargs[k] = expected_new_treq
            return args[0](*args[1:], **kwargs)
    return FakeTestCase()


class MimicNovaTestCase(SynchronousTestCase):
    """
    Tests for :class:`MimicNova`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()

        class FakeRCS(object):
            endpoints = {'mimic_nova': 'mimicnovaurl'}

        self.rcs = FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {'pool': self.pool}

        self.delete_treq = get_fake_treq(
            self, 'DELETE', "mimicnovaurl/behaviors/some_event/behavior_id",
            ((),
             self.expected_kwargs),
            (Response(204), "successfully deleted behavior"))

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
        criteria = [{"server_name": "name_criteria_.*"}]
        behaviors = [{'name': "behavior name",
                      'parameters': {"behavior": "params"}}]

        _treq = get_fake_treq(
            self, 'POST', "mimicnovaurl/behaviors/some_event",
            ((json.dumps({'criteria': criteria,
                          'name': "sequence",
                          'parameters': {"behaviors": behaviors}}),),
             self.expected_kwargs),
            (Response(201), '{"id": "behavior_id"}'))

        test_case = _get_fake_test_case(_treq, self.delete_treq)

        mimic_nova = MimicNova(pool=self.pool, test_case=test_case, treq=_treq)
        d = mimic_nova.sequenced_behaviors(
            self.rcs, criteria, behaviors, event_description="some_event")
        self.assertEqual("behavior_id", self.successResultOf(d))

        self.assertEqual("successfully deleted behavior",
                         self.successResultOf(test_case.cleanup()))

    def test_delete_behavior(self):
        """
        Delete an existing behavior.
        """
        d = MimicNova(pool=self.pool, treq=self.delete_treq).delete_behavior(
            self.rcs, "behavior_id", event_description="some_event")
        self.assertEqual('successfully deleted behavior',
                         self.successResultOf(d))


class MimicIdentityTestCase(SynchronousTestCase):
    """
    Tests for :class:`MimicIdentity`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()
        self.rcs = object()
        self.expected_kwargs = {'pool': self.pool}

        self.delete_treq = get_fake_treq(
            self, 'DELETE',
            "/mimic/v1.1/IdentityControlAPI/behaviors/some_event/behavior_id",
            ((),
             self.expected_kwargs),
            (Response(204), "successfully deleted behavior"))

    def test_sequenced_behaviors(self):
        """
        Cause a sequence of behaviors, and succeeds on 201.  When a test case
        is provided for which a cleanup should be added, delete is added as
        a cleanup.
        """
        criteria = [{"username": "name_criteria_.*"}]
        behaviors = [{'name': "behavior name",
                      'parameters': {"behavior": "params"}}]

        _treq = get_fake_treq(
            self, 'POST',
            "/mimic/v1.1/IdentityControlAPI/behaviors/some_event",
            ((json.dumps({'criteria': criteria,
                          'name': "sequence",
                          'parameters': {"behaviors": behaviors}}),),
             self.expected_kwargs),
            (Response(201), '{"id": "behavior_id"}'))

        test_case = _get_fake_test_case(_treq, self.delete_treq)

        mimic_identity = MimicIdentity(pool=self.pool, test_case=test_case,
                                       treq=_treq)
        d = mimic_identity.sequenced_behaviors(
            "/identity/v2.0", criteria, behaviors,
            event_description="some_event")
        self.assertEqual("behavior_id", self.successResultOf(d))

        self.assertEqual("successfully deleted behavior",
                         self.successResultOf(test_case.cleanup()))


class MimicCLBTestCase(SynchronousTestCase):
    """
    Tests for :class:`MimicCLB`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        class FakeRCS(object):
            endpoints = {'mimic_clb': 'http://host'}

        self.rcs = FakeRCS()
        self.clb = MimicCLB(pool=object(), test_case=self)

    def test_set_clb_attributes(self):
        """
        :func:`set_clb_attributes` calls
        ``PATCH .../loadbalancer/lb_id/attributes`` with given key-value pairs
        """
        stubs = RequestSequence(
            [(("patch", "http://host/loadbalancer/3/attributes", {}, mock.ANY,
               '{"a": "b"}'),
              (204, {}, ""))],
            self.fail)
        self.clb.treq = StubTreq(StringStubbingResource(stubs))
        with stubs.consume(self.fail):
            self.clb.set_clb_attributes(self.rcs, 3, {"a": "b"})

    def test_update_clb_node_status(self):
        """
        :func:`update_clb_node_status` calls
        ``PUT .../loadbalancers/lb_id/nodes/node_id/status`` with given status
        in body
        """
        stubs = RequestSequence(
            [(("put", "http://host/loadbalancers/3/nodes/2/status", {},
               mock.ANY, '{"status": "ONLINE"}'),
              (200, {}, ""))],
            self.fail)
        self.clb.treq = StubTreq(StringStubbingResource(stubs))
        with stubs.consume(self.fail):
            self.clb.update_clb_node_status(self.rcs, 3, 2, "ONLINE")
