"""
Deferred utilities
"""

from twisted.internet import defer
from twisted.internet.task import LoopingCall


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


def timeout_deferred(deferred, timeout, clock):
    """
    Time out a deferred - schedule for it to be canceling it after ``timeout``
    seconds from now, as per the clock.  If it gets cancelled, it errbacks with
    a :class:`twisted.internet.defer.CancelledError`, unless a cancelable
    function is passed to the Deferred's initialization and it callbacks or
    errbacks when cancelled.  (see the documentation for
    :class:`twisted.internet.defer.Deferred`) for more details.

    :param Deferred deferred: Which deferred to time out (cancel)
    :param int timeout: How long before timing out the deferred (in seconds)

    from:  https://twistedmatrix.com/trac/ticket/990
    """
    delayed_call = clock.callLater(timeout, deferred.cancel)

    def cancelTimeout(result):
        if delayed_call.active():
            delayed_call.cancel()
        return result

    deferred.addBoth(cancelTimeout)


class TransientRetryError(Exception):
    """
    Transient error that means that retry should continue retrying
    """
    def __init__(self, wrapped):
        wrapped = wrapped

    def __repr__(self):
        """
        The ``repr`` of :class:`TransientRetryError` includes the ``repr`` of
        the wrapped failure
        """
        return "Transient error [{0!s}]".format(self.wrapped)


def retry(retry_function, interval, clock=None):
    """
    Retries a function every ``interval`` until it succeeds or errbacks with
    something other than :class:`TransientRetryError`

    The ``retry_function`` needs to wrap all transient failures (for which the
    desired effect is to retry) with a :class:`TransientRetryError`.  On
    successful callback from ``retry_function ``, the loop will stop.
    """
    deferred = defer.Deferred()

    # this is needed to cancel an existing operation if one is in progress
    operation_d = []

    def pop_operation(anything):
        operation_d.pop()
        return anything

    def real_retry_function():
        retry = retry_function()
        retry.addBoth(pop_operation)
        retry.addCallback(deferred.callback)
        retry.addErrback(lambda f: f.trap(TransientRetryError))
        retry.addErrback(deferred.errback)
        operation_d.append(retry)
        return retry

    lc = LoopingCall(real_retry_function)

    if clock is not None:  # pragma: no cover
        lc.clock = clock

    def stop_loop(anything):
        if len(operation_d) > 0:
            operation_d[0].addErrback(lambda f: f.trap(defer.CancelledError))
            operation_d[0].cancel()
        lc.stop()
        return anything

    deferred.addBoth(stop_loop)
    lc.start(interval)

    return deferred
