"""
Tests for :mod:`otter.convergence.selfheal`
"""

from effect import Effect, base_dispatcher, raise_, sync_perform
from effect.testing import SequenceDispatcher

import mock

from testtools.matchers import IsInstance

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import selfheal as sh
from otter.log.intents import BoundFields, Log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import (
    GroupState, NoSuchScalingGroupError, ScalingGroupStatus)
from otter.test.utils import (
    CheckFailure, const, conste, intent_func, matches, mock_log,
    nested_sequence, noop, perform_sequence)


class SelfHealTests(SynchronousTestCase):
    """
    Tests for :obj:`SelfHeal`
    """

    def setUp(self):
        self.clock = Clock()
        self.log = mock_log()
        self.patch(sh, "get_groups_to_converge", intent_func("ggtc"))
        self.patch(sh, "check_and_trigger", lambda t, g: t + g)
        self.s = sh.SelfHeal(self.clock, base_dispatcher, "cf", 300.0,
                             self.log)
        self.groups = [
            {"tenantId": "t{}".format(i), "groupId": "g{}".format(i)}
            for i in range(5)]

    def test_call(self):
        """
        ``self.s()`` will setup convergences to be triggered over specified
        time range
        """
        self.s.dispatcher = SequenceDispatcher(
            [(("ggtc", "cf"), const(self.groups))])
        d = self.s()
        self.successResultOf(d)
        calls = self.clock.getDelayedCalls()
        self.assertEqual(self.s._calls, calls)
        for i, c in enumerate(calls):
            self.assertEqual(c.getTime(), i * 60)
            self.assertEqual(c.func, sh.perform)
            self.assertEqual(c.args,
                             (self.s.dispatcher, "t{}g{}".format(i, i)))

    def test_call_err(self):
        """
        ``self.s()`` will log any error and return success
        """
        self.s.dispatcher = SequenceDispatcher(
            [(("ggtc", "cf"), conste(ValueError("h")))])
        d = self.s()
        self.successResultOf(d)
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "selfheal-setup-err",
            otter_service="selfheal")

    def test_call_no_groups(self):
        """
        Gets groups and does nothing if there are no groups
        """
        self.s.dispatcher = SequenceDispatcher([(("ggtc", "cf"), const([]))])
        d = self.s()
        self.successResultOf(d)
        self.assertEqual(self.s._calls, [])
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_call_still_active(self):
        """
        If there are scheduled calls when perform is called, they are
        cancelled and err is logged. Future calls are scheduled as usual
        """
        self.clock.advance(-0.6)
        call1 = self.clock.callLater(1, noop, None)
        call2 = self.clock.callLater(0, noop, None)
        call3 = self.clock.callLater(2, noop, None)
        self.clock.advance(0.6)
        self.s._calls = [call1, call2, call3]
        self.s.dispatcher = SequenceDispatcher(
            [(("ggtc", "cf"), const(self.groups))])
        d = self.s()
        self.successResultOf(d)
        self.log.err.assert_called_once_with(
            matches(IsInstance(RuntimeError)), "selfheal-calls-err", active=2,
            otter_service="selfheal")
        self.assertFalse(call1.active())
        self.assertFalse(call2.active())


class GetGroupsToConvergeTests(SynchronousTestCase):
    """
    Tests for :func:`get_groups_to_converge`
    """
    def test_filtered(self):
        """
        Only convgergence enabled tenants are returned
        """
        conf = {"non-convergence-tenants": ["t1"]}
        groups = [{"tenantId": "t1", "groupId": "g1"},
                  {"tenantId": "t1", "groupId": "g12"},
                  {"tenantId": "t2", "groupId": "g2"},
                  {"tenantId": "t3", "groupId": "g3"}]
        eff = sh.get_groups_to_converge(conf.get)
        seq = [(GetAllValidGroups(), const(groups))]
        self.assertEqual(perform_sequence(seq, eff), groups[2:])


class CheckTriggerTests(SynchronousTestCase):
    """
    Tests for :func:`check_and_trigger`
    """

    def setUp(self):
        self.patch(sh, "trigger_convergence", intent_func("tg"))
        self.state = GroupState("tid", "gid", 'group-name',
                                {}, {}, None, {}, False,
                                ScalingGroupStatus.ACTIVE, desired=2)
        self.manifest = {"state": self.state}

    def test_active_resumed(self):
        """
        Convergence is triggerred on ACTIVE resumed group
        """
        seq = [
            (GetScalingGroupInfo(tenant_id="tid", group_id="gid"),
             const(("group", self.manifest))),
            (BoundFields(effect=mock.ANY,
                         fields=dict(tenant_id="tid", scaling_group_id="gid")),
             nested_sequence([(("tg", "tid", "gid"), noop)]))
        ]
        self.assertIsNone(
            perform_sequence(seq, sh.check_and_trigger("tid", "gid")))

    def test_active_paused(self):
        """
        Convergence is not triggerred on ACTIVE paused group
        """
        self.state.paused = True
        seq = [
            (GetScalingGroupInfo(tenant_id="tid", group_id="gid"),
             const(("group", self.manifest))),
        ]
        self.assertIsNone(
            perform_sequence(seq, sh.check_and_trigger("tid", "gid")))

    def test_inactive_group(self):
        """
        Convergence is not triggerred on in-ACTIVE group
        """
        self.state.status = ScalingGroupStatus.ERROR
        seq = [
            (GetScalingGroupInfo(tenant_id="tid", group_id="gid"),
             const(("group", self.manifest))),
        ]
        self.assertIsNone(
            perform_sequence(seq, sh.check_and_trigger("tid", "gid")))

    def test_group_deleted(self):
        """
        Does nothing if group has been deleted
        """
        seq = [
            (GetScalingGroupInfo(tenant_id="tid", group_id="gid"),
             lambda i: raise_(NoSuchScalingGroupError("tid", "gid"))),
            (Log("selfheal-group-deleted",
                 dict(tenant_id="tid", scaling_group_id="gid")),
             noop)
        ]
        self.assertIsNone(
            perform_sequence(seq, sh.check_and_trigger("tid", "gid")))
