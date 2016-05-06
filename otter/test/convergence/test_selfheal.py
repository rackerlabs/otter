"""
Tests for :mod:`otter.convergence.selfheal`
"""

from kazoo.protocol.states import KazooState

import mock

from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.selfheal import SelfHeal
from otter.test.utils import intent_func, mock_log, patch


class SelfHealTests(SynchronousTestCase):
    """
    Tests for :obj:`SelfHeal`
    """

    def setUp(self):
        self.lock = mock.Mock(specs=["acquire", "release"])
        self.kzc = mock.Mock(specs=["Lock"])
        self.kzc.state = KazooState.CONNECTED
        self.kzc.Lock.return_value = self.lock
        self.clock = Clock()
        self.log = mock_log()
        self.ggtc = patch(
            self, "otter.convergence.selfheal.get_groups_to_converge",
            side_effect=intent_func("ggtc"))
        self.lia = patch(self, "otter.convergence.selfheal.lock_is_acquired")
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
        self.log.msg.assert_called_once_with("self-heal-lock-acquired")

    def test_converge_all_lock_already_acquired(self):
        """
        If lock is already acquired, it will just call self._perform
        """
        self.lia.return_value = succeed(True)
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
            mock.ANY, "self-heal-kz-state", state=KazooState.LOST)

    def test_performs_again(self):
        """
        Calls _perform at every interval
        """
        self.lia.return_value = succeed(True)
        self.s._perform = mock.Mock()
        self.s.startService()
        self.s._perform.assert_called_once_with()
        self.clock.advance(300)
        self.assertEqual(self.s._perform.call_count, 2)

    def test_perform(self):
        """
        Gets groups and sets up convergence to be triggered at future time
        """

    def test_perform_errs(self):
        """
        If getting groups fails, perform just logs the error
        """

    def test_health_check(self):
        pass

    def test_stop_service(self):
        pass
