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


class _TimeOuter(object):
    """
    Helper function that stores state as to whether a Deferred has timed out.
    If so, raises a TimedOutError (eats CancelledError)

    :ivar Deferred deferred: the Deferred to time out
    :ivar float timeout: the amount of time to wait before timing out, in
        seconds
    :ivar str deferred_description: A description of the Deferred or the
        Deferred's purpose - if not provided, defaults to the ``repr`` of the
        Deferred.  To be passed to :class:`TimedOutError` for a pretty
        Exception string.

    :ivar bool timed_out: whether or not the Deferred was timed out by us.
    :ivar IDelayedCall delayed_call: a call to cancel the deferred, scheduled
        ``timeout`` seconds in the future

    based on:  https://twistedmatrix.com/trac/ticket/990
    """
    def __init__(self, deferred, timeout, clock, deferred_description=None):
        self.deferred = deferred
        self.timeout = timeout
        self.deferred_description = deferred_description or repr(deferred)

        self.timed_out = False

        self.delayed_call = clock.callLater(self.timeout, self.time_it_out)

        self.deferred.addErrback(self.convert_cancelled)
        self.deferred.addBoth(self.cancel_timeout)

    def time_it_out(self):
        """
        Cancels the deferred, and also marks us as having been the ones to do
        so.
        """
        self.timed_out = True
        self.deferred.cancel()

    def convert_cancelled(self, f):
        """
        If we timed out the deferred, raise :class:`TimedOutError` if the
        failure is a :class:`CancelledError`.  If the Deferred was created with
        a custom cancellation function that callbacks instead, or errbacks with
        some other error, no :class:`TimedOutError` will be raised.
        """
        if self.timed_out:
            f.trap(defer.CancelledError)
            raise TimedOutError(self.timeout, self.deferred_description)
        return f

    def cancel_timeout(self, result):
        """
        If ``self.deferred`` has been fired, stop the pending call to cancel
        it.
        """
        if self.delayed_call.active():
            self.delayed_call.cancel()
        return result


def timeout_deferred(deferred, timeout, clock, deferred_description=None):
    """
    Time out a deferred - schedule for it to be canceling it after ``timeout``
    seconds from now, as per the clock.  If it gets timed out, it errbacks with
    a :class:`twisted.internet.defer.TimedOutError`, unless a cancelable
    function is passed to the Deferred's initialization and it callbacks or
    errbacks with something else when cancelled.  (see the documentation for
    :class:`twisted.internet.defer.Deferred`) for more details.

    :param Deferred deferred: Which deferred to time out (cancel)
    :param int timeout: How long before timing out the deferred (in seconds)
    :param str deferred_description: A description of the Deferred or the
        Deferred's purpose - if not provided, defaults to the ``repr`` of the
        Deferred.  To be passed to :class:`TimedOutError` for a pretty
        Exception string.
    :param IReactorTime clock: Clock to be used to schedule the timeout -
        used for testing.
    """
    _TimeOuter(deferred, timeout, clock, deferred_description)


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
