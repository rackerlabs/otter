"""
Tests for `LockedTimerService`
"""

from effect import Effect, base_dispatcher, sync_perform
from effect.testing import perform_sequence

from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter import lockedtimerservice as lts
from otter.test.util.test_zk import create_fake_lock
from otter.test.utils import const, iMock, mock_log


class LTService(SynchronousTestCase):
    """
    Tests for :obj:`LockedTimerService`
    """

    def setUp(self):
        self.clock = Clock()
        self.func = iMock(lts.ILockedTimerFunc)
        self.func.log = mock_log()
        self.func.name = "test"
        self.lb, lock = create_fake_lock()
        self.s = lts.LockedTimerService(
            self.clock, base_dispatcher, "/path", 10, self.func, lock=lock)

    def test_func_called_lock_already_acquired(self):
        """
        `self.func` is called if ``call_if_acquired`` returns the fact that
        lock is already acquired
        """
        self.lb.acquired = True
        self.s.startService()
        self.func.call.assert_called_once_with()
        self.assertFalse(self.func.log.msg.called)

    def test_func_called_lock_acquired(self):
        """
        ``self.func`` is called if ``call_if_acquired`` calls effect after
        acquiring the lock and acquired message is logged
        """
        self.lb.acquired = False
        self.lb.acquire_call = (False, None, True)
        self.s.startService()
        self.func.call.assert_called_once_with()
        self.func.log.msg.assert_called_once_with("test-lock-acquired")

    def test_func_not_called(self):
        """
        ``self.func`` is not called if ``call_if_acquired`` returns lock not
        acquired
        """
        self.lb.acquired = False
        self.lb.acquire_call = (False, None, False)
        self.s.startService()
        self.assertFalse(self.func.call.called)

    def test_func_called_again(self):
        """
        ``self.func`` is called again after interval passes
        """
        self.lb.acquired = True
        self.s.startService()
        self.func.call.assert_called_once_with()
        self.clock.advance(10)
        self.assertEqual(len(self.func.call.mock_calls), 2)

    def test_stop_service(self):
        """
        ``stopService`` stops the timer, calls ``func.stop`` and
        releases the lock
        """
        self.test_func_called_lock_already_acquired()
        self.s.stopService()
        # Stop called?
        self.func.stop.assert_called_once_with()
        # lock released?
        self.assertFalse(self.lb.acquired)
        # timer stopped? bad dispatcher will raise error
        self.s.dispatcher = "bad"
        self.clock.advance(10)

    def test_health_check(self):
        """
        ``health_check`` returns whether lock is acquired
        """
        self.lb.acquired = True
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": True}))

        self.lb.acquired = False
        self.assertEqual(
            self.successResultOf(self.s.health_check()),
            (True, {"has_lock": False}))


class CallIfAcquiredTests(SynchronousTestCase):
    """
    Tests for :func:`call_if_acquired`
    """
    def setUp(self):
        self.lb, self.lock = create_fake_lock()

    def test_lock_not_acquired(self):
        """
        When lock is not acquired, it is tried and if failed does not
        call eff
        """
        self.lb.acquired = False
        self.lb.acquire_call = (False, None, False)
        self.assertEqual(
            sync_perform(
                base_dispatcher,
                lts.call_if_acquired(self.lock, Effect("call"))),
            (lts.NOT_CALLED, False))

    def test_lock_acquired(self):
        """
        When lock is not acquired, it is tried and if successful calls eff
        """
        self.lb.acquired = False
        self.lb.acquire_call = (False, None, True)
        seq = [("call", const("eff_return"))]
        self.assertEqual(
            perform_sequence(
                seq,
                lts.call_if_acquired(self.lock, Effect("call"))),
            ("eff_return", True))

    def test_lock_already_acquired(self):
        """
        If lock is already acquired, it will just call eff
        """
        self.lb.acquired = True
        seq = [("call", const("eff_return"))]
        self.assertEqual(
            perform_sequence(
                seq,
                lts.call_if_acquired(self.lock, Effect("call"))),
            ("eff_return", False))
