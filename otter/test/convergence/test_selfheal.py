"""
Tests for :mod:`otter.convergence.selfheal`
"""

from effect.testing import SequenceDispatcher

from kazoo.client import KazooClient
from kazoo.exceptions import LockTimeout
from kazoo.protocol.states import KazooState

import mock

from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import selfheal as sh
from otter.log.intents import BoundFields
from otter.models.intents import GetAllValidGroups, GetScalingGroupInfo
from otter.models.interface import GroupState, ScalingGroupStatus
from otter.test.utils import (
    CheckFailure, const, intent_func, mock_log, nested_sequence, noop, patch,
    perform_sequence, raise_)
from otter.util.zk import GetChildren


class SelfHealTests(SynchronousTestCase):
    """
    Tests for :obj:`SelfHeal`
    """

    def setUp(self):
        self.lock = mock.Mock(specs=["acquire", "release"])
        self.lock.release.return_value = succeed("released")
        self.kzc = mock.Mock(specs=["Lock"])
        self.kzc.state = KazooState.CONNECTED
        self.kzc.Lock.return_value = self.lock
        self.clock = Clock()
        self.log = mock_log()
        self.ggtc = patch(
            self, "otter.convergence.selfheal.get_groups_to_converge",
            side_effect=intent_func("ggtc"))
        self.ila = patch(self, "otter.convergence.selfheal.is_lock_acquired",
                         return_value=succeed(True))
        self.s = sh.SelfHeal("disp", self.kzc, 300, self.log, self.clock, "cf")

    def test_converge_all_lock_not_acquired(self):
        """
        When lock is not acquired, it is tried and if failed does not
        call _perform
        """
        self.ila.return_value = succeed(False)
        self.lock.acquire.return_value = fail(LockTimeout())
        # tests that it is not called
        self.s._perform = lambda: 1 / 0
        self.s.startService()
        self.ila.assert_called_once_with(self.s.disp, self.lock)
        self.lock.acquire.assert_called_once_with(True, 0.1)

    def test_converge_all_lock_acquired(self):
        """
        When lock is not acquired, it is tried and if successful self._perform
        is called
        """
        self.ila.return_value = succeed(False)
        self.lock.acquire.return_value = succeed(True)
        self.s._perform = mock.Mock()
        self.s.startService()
        self.ila.assert_called_once_with(self.s.disp, self.lock)
        self.lock.acquire.assert_called_once_with(True, 0.1)
        self.s._perform.assert_called_once_with("cf", 300)
        self.log.msg.assert_called_once_with(
            "self-heal-lock-acquired", otter_service="selfheal")

    def test_converge_all_lock_already_acquired(self):
        """
        If lock is already acquired, it will just call self._perform
        """
        self.s._perform = mock.Mock()
        self.s.startService()
        self.ila.assert_called_once_with(self.s.disp, self.lock)
        # Lock is not acquired again
        self.assertFalse(self.lock.acquire.called)
        self.s._perform.assert_called_once_with("cf", 300)

    def test_converge_all_kz_not_connected(self):
        """
        If kazoo client is not connected then nothing is done
        """
        self.kzc.state = KazooState.LOST

        def bad_func(*a):
            return 1 / 0

        self.s._perform = self.ila.side_effect = \
            self.lock.acquire.side_effect = bad_func
        self.s.startService()
        self.log.err.assert_called_once_with(
            mock.ANY, "self-heal-kz-state", state=KazooState.LOST,
            otter_service="selfheal")

    def test_performs_again(self):
        """
        Calls _perform at every interval
        """
        self.s._perform = mock.Mock()
        self.s.startService()
        self.s._perform.assert_called_once_with("cf", 300)
        self.clock.advance(300)
        self.assertEqual(self.s._perform.call_count, 2)

    def test_performs_again_on_err(self):
        """
        Calls _perform at every interval even it it fails
        """
        self.s._perform = mock.Mock(return_value=fail(ValueError("h")))
        self.s.startService()
        self.s._perform.assert_called_once_with("cf", 300)
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "self-heal-convergeall-err",
            otter_service="selfheal")
        self.s._perform.return_value = succeed(None)
        self.clock.advance(300)
        self.assertEqual(self.s._perform.call_count, 2)

    @mock.patch("otter.convergence.selfheal.check_and_trigger")
    def test_perform(self, mock_cat):
        """
        Gets groups and sets up convergence to be triggered at future time
        """
        groups = [{"tenantId": "t{}".format(i), "groupId": "g{}".format(i)}
                  for i in range(5)]
        self.s.disp = SequenceDispatcher([(("ggtc", "cf"), const(groups))])
        mock_cat.side_effect = lambda t, g: t + g
        self.s.startService()
        calls = self.clock.getDelayedCalls()
        # Last call will be for next _convere_all call
        self.assertEqual(self.s.calls, calls[:-1])
        for i, c in enumerate(calls[:-1]):
            self.assertEqual(c.getTime(), i * 60)
            self.assertEqual(c.func, sh.perform)
            self.assertEqual(c.args, (self.s.disp, "t{}g{}".format(i, i)))

    def test_perform_no_groups(self):
        """
        Gets groups and doesnt do anything if there are no groups
        """
        self.s.disp = SequenceDispatcher([(("ggtc", "cf"), const([]))])
        self.s.startService()
        self.assertEqual(self.s.calls, [])
        calls = self.clock.getDelayedCalls()
        self.assertEqual(len(calls), 1)

    def test_perform_still_active(self):
        """
        If there are scheduled calls when perform is called, they are
        cancelled and err is logged. Future calls are scheduled as usual
        """
        call1 = self.clock.callLater(1, noop, 2)
        call2 = self.clock.callLater(2, noop, 3)
        self.s.calls = [call1, call2]
        self.test_perform()
        self.log.err.assert_called_once_with(
            mock.ANY, "self-heal-calls-err", active=2,
            otter_service="selfheal")
        self.assertFalse(call1.active())
        self.assertFalse(call2.active())

    def test_perform_errs(self):
        """
        If getting groups fails, perform just logs the error
        """
        self.s.disp = SequenceDispatcher([
            (("ggtc", "cf"), lambda i: raise_(ValueError("huh")))])
        self.s.startService()
        self.assertEqual(self.s.calls, [])
        self.log.err.assert_called_once_with(
            CheckFailure(ValueError), "self-heal-convergeall-err",
            otter_service="selfheal")

    def test_health_check(self):
        """
        Health check returns about lock being acquired
        """
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": True}))
        self.ila.return_value = succeed(False)
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": False}))

    def test_stop_service(self):
        """
        `stopService` will stop the timer, cancel any scheduled calls and
        release lock
        """
        self.test_perform()
        calls = self.s.calls[:]
        d = self.s.stopService()
        # calls cancelled
        self.assertTrue(all(not c.active() for c in calls))
        # lock released
        self.lock.release.assert_called_with()
        self.assertEqual(self.successResultOf(d), "released")
        # timer stopped; having bad dispatcher would raise error if perform
        # was called again
        self.s.disp = "bad"
        self.clock.advance(300)


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


class IsLockAcquiredTests(SynchronousTestCase):
    """
    Tests for :func:`is_lock_acquired` and :func:`is_lock_acquired_eff`
    """

    def test_eff_no_children(self):
        """
        If lock node does not have any children, it does not have lock
        """
        lock = mock.Mock(spec=KazooClient, path="/lock")
        seq = [(GetChildren("/lock"), const([]))]
        self.assertFalse(perform_sequence(seq, sh.is_lock_acquired_eff(lock)))

    def test_eff_has_lock(self):
        """
        Lock node's first child belongs to given object. Hence has the lock
        """
        prefix = "someprefix__lock__"
        lock = mock.Mock(spec=KazooClient, path="/lock", prefix=prefix)
        children = ["errrprefix__lock__0000000004",
                    "{}0000000001".format(prefix),
                    "whyprefix__lock__0000000002"]
        seq = [(GetChildren("/lock"), const(children))]
        self.assertTrue(perform_sequence(seq, sh.is_lock_acquired_eff(lock)))

    def test_eff_no_lock(self):
        """
        If lock's node is not the first in the sorted list of children, then
        it does not have the lock
        """
        prefix = "whyprefix__lock__"
        lock = mock.Mock(spec=KazooClient, path="/lock", prefix=prefix)
        children = ["errrprefix__lock__0000000004",
                    "someprefix__lock__0000000001",
                    "{}0000000002".format(prefix)]
        seq = [(GetChildren("/lock"), const(children))]
        self.assertFalse(perform_sequence(seq, sh.is_lock_acquired_eff(lock)))

    def test_is_lock_acquired_performs(self):
        """
        `is_lock_acquired` just performs the effect returned from
        `is_lock_acquired_eff` with given dispatcher
        """
        self.patch(sh, "is_lock_acquired_eff", intent_func("ilae"))
        disp = SequenceDispatcher([(("ilae", "lock"), const("ret"))])
        self.assertEqual(
            self.successResultOf(sh.is_lock_acquired(disp, "lock")),
            "ret")
