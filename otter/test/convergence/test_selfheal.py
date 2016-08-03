"""
Tests for :mod:`otter.convergence.selfheal`
"""

from effect import Effect
from effect.testing import SequenceDispatcher

from kazoo.exceptions import LockTimeout

import mock

from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import selfheal as sh
from otter.log.intents import BoundFields, Log
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import (
    GroupState, NoSuchScalingGroupError, ScalingGroupStatus)
from otter.test.util.test_zk import ZKCrudModel, ZKLock
from otter.test.utils import (
    CheckFailure, const, intent_func, mock_log, nested_sequence, noop, patch,
    perform_sequence, raise_)
from otter.util.zk import AcquireLock, GetChildren


class SelfHealTests(SynchronousTestCase):
    """
    Tests for :obj:`SelfHeal`
    """

    def setUp(self):
        self.kzc = ZKCrudModel()
        self.clock = Clock()
        self.log = mock_log()
        self.ggtc = patch(
            self, "otter.convergence.selfheal.get_groups_to_converge",
            side_effect=intent_func("ggtc"))
        self.s = sh.SelfHeal("disp", self.kzc, 300, self.log, self.clock, "cf")

    def test_setup_again(self):
        """
        Calls _setup_if_locked at every interval
        """
        self.s._setup_if_locked = mock.Mock()
        self.s.startService()
        self.s._setup_if_locked.assert_called_once_with("cf", 300)
        self.clock.advance(300)
        self.assertEqual(self.s._setup_if_locked .call_count, 2)

    def test_setup_again_on_err(self):
        """
        Calls _setup_if_locked at every interval even it it fails
        """
        self.s._setup_if_locked = mock.Mock(return_value=fail(ValueError("h")))
        self.s.startService()
        self.s._setup_if_locked.assert_called_once_with("cf", 300)
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "self-heal-setup-err",
            otter_service="selfheal")
        self.s._setup_if_locked.return_value = succeed(None)
        self.clock.advance(300)
        self.assertEqual(self.s._setup_if_locked.call_count, 2)

    @mock.patch("otter.convergence.selfheal.check_and_trigger")
    def test_setup_convergences(self, mock_cat):
        """
        Gets groups and sets up convergence to be triggered at future time
        """
        groups = [{"tenantId": "t{}".format(i), "groupId": "g{}".format(i)}
                  for i in range(5)]
        self.s.disp = SequenceDispatcher([(("ggtc", "cf"), const(groups))])
        mock_cat.side_effect = lambda t, g: t + g
        # Let _setup_if_locked directly call _setup_convergences to avoid
        # going through _setup_if_locked
        self.s._setup_if_locked = self.s._setup_convergences
        self.s.startService()
        calls = self.clock.getDelayedCalls()
        # Last call will be for next _convere_all call
        self.assertEqual(self.s.calls, calls[:-1])
        for i, c in enumerate(calls[:-1]):
            self.assertEqual(c.getTime(), i * 60)
            self.assertEqual(c.func, sh.perform)
            self.assertEqual(c.args, (self.s.disp, "t{}g{}".format(i, i)))

    def test_setup_convergences_no_groups(self):
        """
        Gets groups and does nothing if there are no groups
        """
        self.s.disp = SequenceDispatcher([(("ggtc", "cf"), const([]))])
        # Let _setup_if_locked directly call _setup_convergences to avoid
        # going through _setup_if_locked
        self.s._setup_if_locked = self.s._setup_convergences
        self.s.startService()
        self.assertEqual(self.s.calls, [])
        calls = self.clock.getDelayedCalls()
        self.assertEqual(len(calls), 1)

    def test_setup_convergences_still_active(self):
        """
        If there are scheduled calls when perform is called, they are
        cancelled and err is logged. Future calls are scheduled as usual
        """
        call1 = self.clock.callLater(1, noop, 2)
        call2 = self.clock.callLater(2, noop, 3)
        self.s.calls = [call1, call2]
        self.test_setup_convergences()
        self.log.err.assert_called_once_with(
            mock.ANY, "self-heal-calls-err", active=2,
            otter_service="selfheal")
        self.assertFalse(call1.active())
        self.assertFalse(call2.active())

    def test_setup_convergences_errs(self):
        """
        If getting groups fails, perform just logs the error
        """
        self.s.disp = SequenceDispatcher([
            (("ggtc", "cf"), lambda i: raise_(ValueError("huh")))])
        # Let _setup_if_locked directly call _setup_convergences to avoid
        # going through _setup_if_locked
        self.s._setup_if_locked = self.s._setup_convergences
        self.s.startService()
        self.assertEqual(self.s.calls, [])
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "self-heal-setup-err",
            otter_service="selfheal")

    def test_health_check(self):
        """
        Health check returns about lock being acquired
        """
        self.patch(sh, "is_lock_acquired", intent_func("ila"))
        self.s.disp = SequenceDispatcher([
            (("ila", self.s.lock), const(True))])
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": True}))
        self.s.disp = SequenceDispatcher([
            (("ila", self.s.lock), const(False))])
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": False}))

    def test_stop_service(self):
        """
        `stopService` will stop the timer, cancel any scheduled calls and
        release lock
        """
        self.s.lock.acquired = True
        self.test_setup_convergences()
        calls = self.s.calls[:]
        d = self.s.stopService()
        # calls cancelled
        self.assertTrue(all(not c.active() for c in calls))
        # lock released
        self.assertIsNone(self.successResultOf(d))
        self.assertFalse(self.s.lock.acquired)
        # timer stopped; having bad dispatcher would raise error if perform
        # was called again
        self.s.disp = "bad"
        self.clock.advance(300)

    def test_setup_if_locked(self):
        """
        :func:`_setup_if_locked` calls ``self._setup_convergences`` through
        ``call_if_acquired``
        """

        def cia(l, e):
            self.assertIs(l, self.s.lock)
            return e

        self.patch(sh, "call_if_acquired", cia)
        self.s.disp = SequenceDispatcher([])
        self.s._setup_convergences = mock.Mock(return_value=succeed(True))
        d = self.s._setup_if_locked("cf", 35)
        self.assertIsNone(self.successResultOf(d))
        self.s._setup_convergences.assert_called_once_with("cf", 35)
        self.log.msg.assert_called_once_with(
            "self-heal-lock-acquired", otter_service="selfheal")


class CallIfAcquiredTests(SynchronousTestCase):
    """
    Tests for :func:`call_if_acquired`
    """
    def setUp(self):
        self.patch(sh, "is_lock_acquired", intent_func("ila"))

    def test_lock_not_acquired(self):
        """
        When lock is not acquired, it is tried and if failed does not
        call eff
        """
        lock = object()
        seq = [(("ila", lock), const(False)),
               (AcquireLock(lock, True, 0.1), lambda i: raise_(LockTimeout()))]
        self.assertFalse(
            perform_sequence(seq, sh.call_if_acquired(lock, Effect("call"))))

    def test_lock_acquired(self):
        """
        When lock is not acquired, it is tried and if successful calls eff
        """
        lock = object()
        seq = [(("ila", lock), const(False)),
               (AcquireLock(lock, True, 0.1), const(True)),
               ("call", noop)]
        self.assertTrue(
            perform_sequence(seq, sh.call_if_acquired(lock, Effect("call"))))

    def test_lock_already_acquired(self):
        """
        If lock is already acquired, it will just call eff
        """
        lock = object()
        seq = [(("ila", lock), const(True)),
               ("call", noop)]
        self.assertFalse(
            perform_sequence(seq, sh.call_if_acquired(lock, Effect("call"))))


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


class IsLockAcquiredTests(SynchronousTestCase):
    """
    Tests for :func:`is_lock_acquired` and :func:`is_lock_acquired_eff`
    """

    def test_no_children(self):
        """
        If lock node does not have any children, it does not have lock
        """
        lock = ZKLock("client", "/lock")
        seq = [(GetChildren("/lock"), const([]))]
        self.assertFalse(perform_sequence(seq, sh.is_lock_acquired(lock)))

    def test_has_lock(self):
        """
        Lock node's first child belongs to given object. Hence has the lock
        """
        prefix = "someprefix__lock__"
        lock = ZKLock("client", "/lock")
        lock.prefix = prefix
        children = ["errrprefix__lock__0000000004",
                    "{}0000000001".format(prefix),
                    "whyprefix__lock__0000000002"]
        seq = [(GetChildren("/lock"), const(children))]
        self.assertTrue(perform_sequence(seq, sh.is_lock_acquired(lock)))

    def test_no_lock(self):
        """
        If lock's node is not the first in the sorted list of children, then
        it does not have the lock
        """
        prefix = "whyprefix__lock__"
        lock = ZKLock("client", "/lock")
        lock.prefix = prefix
        children = ["errrprefix__lock__0000000004",
                    "someprefix__lock__0000000001",
                    "{}0000000002".format(prefix)]
        seq = [(GetChildren("/lock"), const(children))]
        self.assertFalse(perform_sequence(seq, sh.is_lock_acquired(lock)))
