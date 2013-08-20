"""
Deferred utilities
"""

from twisted.internet import defer


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


def retry(do_work, can_retry=None, next_interval=None, clock=None):
    """
    Retries the `do_work` function if it does not succeed and the ``can_retry``
    callable returns ``True``.  The next time the `do_work` function is retried
    is dependent upon the return value of the function ``next_interval``, which
    should return the number of seconds before the next attempt.

    The ``can_retry`` function will only be called upon ``do_work`` error, and
    should accept a failure and return a boolean.

    :param callable do_work: function to be retried - should take no arguments
        and can be either synchronous or return a deferred
    :param callable can_retry: function that takes a failure and returns a
        boolean representing whether or not the next attempt should be made, or
        if all retries should be aborted.  Should be synchronous.
    :param callable next_interval: function that takes a failure and returns
        the number of seconds until the next attempt as a float.  Should be synchronous.
    :param clock: clock to be used to retry - used for testing purposes

    :return: a Deferred which fires with the result of the ``do_work``,
        if successful, or the failure of the ``do_work``, if cannot be retried
    """
    deferred = defer.Deferred()

    # this is needed to cancel an existing operation if one is in progress
    operation_d = []
    delayed_call = [None]
    canceled = [False]

    def pop_operation(anything):
        operation_d.pop()
        return anything

    def handle_failure(f):
        # if the overall deferred is cancelled, this will be cancelled too.
        # if so, do not retry.
        if canceled[0] or not can_retry(f):
            return f

        next_delay = next_interval(f)
        delayed_call.append(clock.callLater(next_delay, real_do_work))

    def real_do_work():
        delayed_call.pop()
        work_d = defer.maybeDeferred(do_work)
        operation_d.append(work_d)

        work_d.addBoth(pop_operation)
        work_d.addCallback(deferred.callback)
        work_d.addErrback(handle_failure)
        work_d.addErrback(deferred.errback)
        return work_d

    def stop_in_progress(anything):
        canceled[0] = True

        if len(delayed_call) > 0 and delayed_call[0] is not None:
            delayed_call[0].cancel()

        if len(operation_d) > 0:
            operation_d[0].addErrback(lambda f: f.trap(defer.CancelledError))
            operation_d[0].cancel()

        return anything

    deferred.addBoth(stop_in_progress)
    real_do_work()

    return deferred
