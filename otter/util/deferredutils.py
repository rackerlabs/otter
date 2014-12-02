"""
Deferred utilities
"""

from twisted.internet import defer

from otter.util.retry import retry

from pyrsistent import freeze

from functools import wraps
from collections import defaultdict


def unwrap_first_error(possible_first_error):
    """
    Failures returned by :meth:`defer.gatherResults` are failures that wrap
    a :class:`defer.FirstError`, which wraps the inner failure.

    Checks failure to see if it is a defer.FirstError.  If it is, recursively
    gets the underlying failure that it wraps (in case it is a first error
    wrapping a first error, etc.)

    :param possible_first_error: a failure that may wrap a
        :class:`defer.FirstError`
    :type possible_first_error: :class:`Failure`

    :return: :class:`Failure` that is under any/all the :class:`defer.FirstError`
    """
    if possible_first_error.check(defer.FirstError):
        return unwrap_first_error(possible_first_error.value.subFailure)
    return possible_first_error  # not a defer.FirstError


def ignore_and_log(failure, exception_type, log, msg):
    """
    Ignore the given exception type and log it. This method is to be used as errback handler

    :param failure: `Failure` instance representing the error
    :param exception_type: Exception class that needs to be trapped
    :param log: A bound logger
    :param msg: message to be logged

    :return: None if exception is trapped. Otherwise, raises other error
    """
    failure.trap(exception_type)
    log.msg(msg, reason=failure)


class TimedOutError(Exception):
    """
    Exception that gets raised by timeout_deferred
    """
    def __init__(self, timeout, deferred_description):
        super(TimedOutError, self).__init__(
            "{desc} timed out after {timeout} seconds.".format(
                desc=deferred_description, timeout=timeout))


def timeout_deferred(deferred, timeout, clock, deferred_description=None):
    """
    Time out a deferred - schedule for it to be canceling it after ``timeout``
    seconds from now, as per the clock.

    If it gets timed out, it errbacks with a :class:`TimedOutError`, unless a
    cancelable function is passed to the ``Deferred``'s initialization and it
    callbacks or errbacks with something else when cancelled.
    (see the documentation for :class:`twisted.internet.defer.Deferred`)
    for more details.

    :param Deferred deferred: Which deferred to time out (cancel)
    :param int timeout: How long before timing out the deferred (in seconds)
    :param str deferred_description: A description of the Deferred or the
        Deferred's purpose - if not provided, defaults to the ``repr`` of the
        Deferred.  To be passed to :class:`TimedOutError` for a pretty
        Exception string.
    :param IReactorTime clock: Clock to be used to schedule the timeout -
        used for testing.

    :return: ``None``

    based on:  https://twistedmatrix.com/trac/ticket/990
    """
    timed_out = [False]

    def time_it_out():
        timed_out[0] = True
        deferred.cancel()

    delayed_call = clock.callLater(timeout, time_it_out)

    def convert_cancelled(f):
        # if the failure is CancelledError, and we timed it out, convert it
        # to a TimedOutError.  Otherwise, propagate it.
        if timed_out[0]:
            f.trap(defer.CancelledError)
            raise TimedOutError(timeout, deferred_description)
        return f

    deferred.addErrback(convert_cancelled)

    def cancel_timeout(result):
        # stop the pending call to cancel the deferred if it's been fired
        if delayed_call.active():
            delayed_call.cancel()
        return result

    deferred.addBoth(cancel_timeout)


def retry_and_timeout(do_work, timeout, can_retry=None, next_interval=None,
                      clock=None, deferred_description=None):
    """
    Retry a function until the function succeeds or timeout has been reached.
    This is just a composition of :func:`timeout_deferred` and :func:`retry`
    for convenience.  Please see their respective arguments.
    """
    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    d = retry(do_work, can_retry=can_retry, next_interval=next_interval,
              clock=clock)
    timeout_deferred(d, timeout, clock=clock,
                     deferred_description=deferred_description)
    return d


class DeferredPool(object):
    """
    Keep track of a pool of deferreds to finish, and notify waiting deferreds
    when all in the pool are finished.

    This is to be used rather than ``gatherDeferreds`` or ``DeferredList`` in
    cases where maybe one or two more ``Deferreds`` might be added to the pool
    while waiting for it to empty.  This should be an edge case though.

    From http://www.verious.com/tool/graceful-shutdown-of-a-twisted-service-with-outstanding-deferreds/
    """
    def __init__(self):
        self._pool = set()
        self._waiting = []

    def _fired(self, result, deferred):
        """
        Remove a pooled ``Deferred`` that has fired from the pool.  If removing
        this deferred empties the pool, fire all the ``Deferreds`` waiting
        for the pool to empty.

        Also acts as a passthrough that returns whatever result was passed to it
        """
        self._pool.remove(deferred)
        self._if_empty_notify()
        return result

    def add(self, deferred):
        """
        Add a ``Deferred`` to the pool.
        """
        self._pool.add(deferred)
        deferred.addBoth(self._fired, deferred)

    def _if_empty_notify(self):
        """
        Checks to see if the pool is empty.  If it is, notifies all the waiting
        callbacks.
        """
        if not self._pool:
            waiting, self._waiting = self._waiting, []
            for waiter in waiting:
                waiter.callback(None)

    def notify_when_empty(self):
        """
        Return a deferred that fires (with None) when the pool empties (which
        may be immediately)
        """
        d = defer.Deferred()
        self._waiting.append(d)
        self._if_empty_notify()
        return d

    def __len__(self):
        """
        Return number of deferreds in the pool
        """
        return len(self._pool)

    def __contains__(self, deferred):
        """
        Return True if given deferred is in the pool. False if not
        """
        return deferred in self._pool


def log_with_time(result, reactor, log, start, msg, time_kwarg=None):
    """
    Log `msg` with time taken

    :param result: result of deferred callback
    :param reactor: `IReactorTime` provider
    :param log: A bound logger
    :param start: start seconds
    :param msg: Message to display with time taken
    :param time_kwarg: kwarg used to call msg with time taken
    """
    time_taken = reactor.seconds() - start
    msg = '{msg} in {t} seconds'.format(msg=msg, t=time_taken)
    if time_kwarg:
        log.msg(msg, **{time_kwarg: time_taken})
    else:
        log.msg(msg)
    return result


def with_lock(reactor, lock, func, log=None, acquire_timeout=None, release_timeout=None):
    """
    Context manager for any lock object that contains acquire() and release() methods
    """
    if log:
        log.msg('Starting lock acquisition')
    d = defer.maybeDeferred(lock.acquire)
    if acquire_timeout is not None:
        timeout_deferred(d, acquire_timeout, reactor, 'Lock acquisition')
    if log:
        d.addCallback(log_with_time, reactor, log, reactor.seconds(),
                      'Lock acquisition', 'acquire_time')
        d.addErrback(log_with_time, reactor, log, reactor.seconds(),
                     'Lock acquisition failed')

    def release_lock(result):
        if log:
            log.msg('Starting lock release')
        d = defer.maybeDeferred(lock.release)
        if release_timeout is not None:
            timeout_deferred(d, release_timeout, reactor, 'Lock release')
        if log:
            d.addCallback(
                log_with_time, reactor, log, reactor.seconds(), 'Lock release', 'release_time')
        return d.addCallback(lambda _: result)

    def lock_acquired(_):
        d = defer.maybeDeferred(func).addBoth(release_lock)
        return d

    d.addCallback(lock_acquired)
    return d


def delay(result, reactor, seconds):
    """
    Delays the result by `seconds`.

    :param result: Result to be returned after `seconds` have passed
    :param reactor: IReactorTime provider
    :param seconds: Number of seconds to delay

    :return: `result` after `seconds` have passed
    """
    d = defer.Deferred()
    reactor.callLater(seconds, d.callback, result)
    return d


def wait(ignore_kwargs=True):
    """
    Return decorator that wraps a function by waiting for its result when its called
    multiple times and its result from first call is not yet ready. Basically disallows
    re-entrancy for Deferred returning functions

    :param bool ignore_kwargs: Ignore keyword arguments of wrapped function when waiting
    :return: A decorator that can wrap function to wait
    """
    waiters = defaultdict(list)
    waiting = {}

    def release_waiters(r, method, k):
        for waiter in waiters[k]:
            method(waiter, r)
        del waiters[k], waiting[k]
        return r

    def wrap(func):

        @wraps(func)
        def wrapped_f(*args, **kwargs):
            k = freeze(args) if ignore_kwargs else freeze((args, kwargs))
            if k in waiting:
                d = defer.Deferred()
                waiters[k].append(d)
            else:
                d = defer.maybeDeferred(func, *args, **kwargs)
                waiting[k] = d
                d.addCallback(release_waiters, defer.Deferred.callback, k)
                d.addErrback(release_waiters, defer.Deferred.errback, k)
            return d

        return wrapped_f

    return wrap
