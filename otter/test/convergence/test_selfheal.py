"""
Tests for :mod:`otter.convergence.selfheal`
"""

from effect.testing import SequenceDispatcher

from kazoo.protocol.states import KazooState

import mock

from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.selfheal import SelfHeal
from otter.convergence import selfheal as sh
from otter.test.utils import CheckFailure, const, intent_func, mock_log, noop, patch, raise_


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
        self.lia = patch(self, "otter.convergence.selfheal.lock_is_acquired",
                         return_value=succeed(True))
        self.s = SelfHeal("disp", self.kzc, 300, self.log, self.clock, "cf")

    def test_converge_all_lock_not_acquired(self):
        """
        When lock is not acquired, it is tried and if failed does not
        call _perform
        """
        self.lia.return_value = succeed(False)
        self.lock.acquire.return_value = succeed(False)
        # tests that it is not called
        self.s._perform = lambda: 1 / 0
        self.s.startService()
        self.lock.acquire.assert_called_once_with(False, None)

    def test_converge_all_lock_acquired(self):
        """
        When lock is not acquired, it is tried and if successful self._perform
        is called
        """
        self.lia.return_value = succeed(False)
        self.lock.acquire.return_value = succeed(True)
        self.s._perform = mock.Mock()
        self.s.startService()
        self.lock.acquire.assert_called_once_with(False, None)
        self.s._perform.assert_called_once_with()
        self.log.msg.assert_called_once_with(
            "self-heal-lock-acquired", otter_service="selfheal")

    def test_converge_all_lock_already_acquired(self):
        """
        If lock is already acquired, it will just call self._perform
        """
        self.s._perform = mock.Mock()
        self.s.startService()
        # Lock is not acquired again
        self.assertFalse(self.lock.acquire.called)
        self.s._perform.assert_called_once_with()

    def test_converge_all_kz_not_connected(self):
        """
        If kazoo client is not connected then nothing is done
        """
        self.kzc.state = KazooState.LOST

        def bad_func(*a):
            return 1 / 0

        self.s._perform = self.lia.side_effect = \
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
        self.s._perform.assert_called_once_with()
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
        self.assertEqual(self.s.calls, calls[:-1])
        for i, c in enumerate(calls[:-1]):
            self.assertEqual(c.getTime(), i * 59)
            self.assertEqual(c.func, sh.perform)
            self.assertEqual(c.args, (self.s.disp, "t{}g{}".format(i, i)))

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
            CheckFailure(ValueError), "self-heal-err",
            otter_service="selfheal")

    def test_health_check(self):
        """
        Health check returns about lock being acquired
        """
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": True}))
        self.lia.return_value = succeed(False)
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
