"""
A service that ensures only one node calls a given function on interval basis
"""

from effect import ComposedDispatcher, Effect, TypeDispatcher
from effect.do import do, do_return

from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.internet.defer import maybeDeferred

from txeffect import deferred_performer, perform

from zope.interface import Attribute, Interface

from otter.util import zk


class ILockedTimerFunc(Interface):
    """
    Object used by :obj:`LockedTimerService` that provides the function to
    call on interval basis.
    """
    name = Attribute("name of this service")
    log = Attribute("This service's logger")

    def call():
        """
        This will be called on interval basis by ``LockedTimerService``. It can
        return a `Deferred`.
        """

    def stop():
        """
        This will be called when ``LockedTimerService`` is shutting down
        """


class LockedTimerService(MultiService, object):
    """
    A service that calls function on interval basis. This service is shared
    among multiple hosts using a Zookeeper lock and ensures only one node
    calls the function at any given interval.

    :ivar dispatcher: Effect dispatcher to perform all effects
        (ZK, CASS, log, etc)
    :type dispatcher: Either :obj:`ComposedDispatcher` or :obj:`TypeDispatcher`
    :ivar IReactorTime clock: Reactor providing timing APIs
    :ivar log: Twisted logger with .msg and .err methods
    :ivar lock: Lock object from :obj:`TxKazooClient`
    :ivar str name: Name of the service used when logging
    """

    def __init__(self, clock, dispatcher, path, interval, func, lock=None):
        """
        :var float interval: time between calling ``func`` again
        :var str path: path to acquire lock on
        :var :obj:`ILockedTimerFunc` func: timer function that will be called
            on interval basis
        :var lock: lock object used primarily for testing. If not given, a new
            lock will be created from ``zk.PollingLock``
        """
        super(LockedTimerService, self).__init__()
        self.dispatcher = dispatcher
        self.lock = lock or zk.PollingLock(dispatcher, path)
        self.clock = clock
        self.func = func
        timer = TimerService(interval, self._lock_and_call)
        timer.clock = clock
        timer.setServiceParent(self)

    def stopService(self):
        """
        Stop service by calling ``self.func.stop`` and releasing the lock
        """
        super(LockedTimerService, self).stopService()
        return maybeDeferred(self.func.stop).addCallback(
            lambda _: self.lock.release())

    def health_check(self):
        """
        Return about whether this object has lock
        """
        d = self.lock.is_acquired()
        return d.addCallback(lambda b: (True, {"has_lock": b}))

    def _lock_and_call(self):
        """
        Call ``func`` if this node has the lock
        """
        class DoFunc(object):
            pass

        @deferred_performer
        def func_performer(d, i):
            return maybeDeferred(self.func.call)

        def log_acquired(r):
            result, acquired = r
            if acquired:
                self.func.log.msg("{}-lock-acquired".format(self.func.name))
            return result

        dispatcher = ComposedDispatcher([
            TypeDispatcher({DoFunc: func_performer}), self.dispatcher])
        d = perform(
            dispatcher,
            call_if_acquired(self.lock, Effect(DoFunc())))
        return d.addCallback(log_acquired)


# Sentinet object representing the fact that eff passed in ``call_if_acquired``
# was not called
NOT_CALLED = object()


@do
def call_if_acquired(lock, eff):
    """
    Call ``eff`` if ``lock`` is acquired. If not, try to acquire the lock
    and call ``eff``. This function is different from
    :func:`otter.util.deferredutils.with_lock` where this does not release
    the lock after calling ``func``. Also it expects that lock may already be
    acquired.

    :param lock: Lock object from :obj:`TxKazooClient`
    :param eff: ``Effect`` to call if lock is/was acquired

    :return: (eff return, lock acquired bool) tuple. first element may be
        ``NOT_CALLED`` of eff was not called
    :rtype: ``Effect`` of ``bool``
    """
    if (yield lock.is_acquired_eff()):
        ret = yield eff
        yield do_return((ret, False))
    else:
        if (yield lock.acquire_eff(False, None)):
            ret = yield eff
            yield do_return((ret, True))
        else:
            yield do_return((NOT_CALLED, False))
