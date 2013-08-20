"""
Deferred utilities
"""

from twisted.internet import defer

from otter.util.retry import retry


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


def retry_and_timeout(do_work, timeout, can_retry=None, next_interval=None,
                      clock=None):
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
    timeout_deferred(d, timeout, clock=clock)
    return d
