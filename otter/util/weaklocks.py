from weakref import WeakValueDictionary

from twisted.internet.defer import DeferredLock


class WeakLocks(object):
    """
    A cache of DeferredLocks that gets garbage collected after the lock has
    been utilized
    """

    def __init__(self):
        self._locks = WeakValueDictionary()

    def get_lock(self, key):
        """
        Get lock based on key. If no lock exists, create one.

        :param key: Some arbitrary key
        :return: :class:`DeferredLock`
        """
        lock = self._locks.get(key)
        if not lock:
            lock = DeferredLock()
            self._locks[key] = lock
        return lock
