from otter.util.weaklocks import WeakLocks

from twisted.internet.defer import DeferredLock
from twisted.trial.unittest import SynchronousTestCase


class WeakLocksTests(SynchronousTestCase):
    """
    Tests for `WeakLocks`
    """

    def setUp(self):
        """
        Sample `WeakLocks` object
        """
        self.locks = WeakLocks()

    def test_returns_deferlock(self):
        """
        `get_lock` returns a `DeferredLock`
        """
        self.assertIsInstance(self.locks.get_lock('a'), DeferredLock)

    def test_same_lock(self):
        """
        `get_lock` on same uuid returns same `DeferredLock`
        """
        self.assertIs(self.locks.get_lock('a'), self.locks.get_lock('a'))

    def test_diff_lock(self):
        """
        `get_lock` on different uuid returns different `DeferredLock`
        """
        self.assertIsNot(self.locks.get_lock('a'), self.locks.get_lock('b'))
