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
    timed_out = []

    def time_it_out():
        timed_out.append(True)
        deferred.cancel()

    delayed_call = clock.callLater(timeout, time_it_out)

    def convert_cancelled(f):
        # if the failure is CancelledError, and we timed it out, convert it
        # to a TimedOutError.  Otherwise, propagate it.
        if timed_out:
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
