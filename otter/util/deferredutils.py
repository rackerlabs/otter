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


class _Retrier(object):
    """
    Helper class used to implement and to store the state of retrying an
    operation.  To be called by :py:func:``retry``

    :ivar callable do_work: function to be retried - should take no arguments
        and can be either synchronous or return a deferred
    :ivar callable can_retry: function that takes a failure and returns a
        boolean representing whether or not the next attempt should be made, or
        if all retries should be aborted.  Should be synchronous.
    :ivar callable next_interval: function that takes a failure and returns
        the number of seconds until the next attempt as a float.  Should be
        synchronous.

    :ivar Clock clock: clock to be used to retry - used for testing purposes

    :ivar Deferred deferred: the :class:`Deferred` that will callback with
        either the eventualy success of the possibly-retried ``do_work``
        function or its failure, for whatever reason.

    :ivar Deferred current_work: the :class:Deferred` corresponding to the
        current work being done by ``do_work``.  Needs to be cancelled if
        ``self.deferred`` is fired due to external reasons (e.g. it is
        cancelled).
    :ivar Deferred delayed_call: the :class:`IDelayedCall` corresponding to the
        next scheduled call of ``do_work``.  Needs to be cancelled if
        ``self.deferred`` is fired due to external reasons (e.g. it is
        cancelled).
    :ivar bool terminated: a boolean representing whether ``self.deferred`` has
        been terminated early (likely due to cancellation of ``self.deferred``)
    """
    def __init__(self, do_work, can_retry, next_interval, clock):
        self.do_work = do_work
        self.can_retry = can_retry
        self.next_interval = next_interval
        self.clock = clock

        self.deferred = defer.Deferred()
        self.deferred.addBoth(self.handle_early_termination)

        self.current_work = None
        self.delayed_call = None
        self.terminated = False

    def clear_current_work(self, anything):
        """
        To be used as a passthrough that also clears out the current work.
        """
        self.current_work = None
        return anything

    def handle_failure(self, f):
        """
        On a failure, either propagate the failure if it is terminal (and
        canceling ``self.deferred`` is terminal, no matter what
        ``self.can_retry`` has to say about it), or schedule the next retry
        of ``self.do_work``
        """
        if self.terminated or not self.can_retry(f):
            return f

        self.delayed_call = self.clock.callLater(self.next_interval(f),
                                                 self.do_real_work)

    def handle_early_termination(self, anything):
        """
        If ``self.deferred`` is cancelled, or for some reason (no one should
        do this) callbacked outside of the context of ``do_work`` succeeding or
        terminally failing, then the work already in progress and scheduled
        needs to be cancelled.

        The result is also propagated.
        """
        if self.delayed_call is not None:
            self.delayed_call.cancel()

        if self.current_work is not None:
            self.terminated = True
            # make sure to eat the cancelled error, so it doesn't get gc-ed and
            # logged
            self.current_work.addErrback(lambda f: f.trap(defer.CancelledError))
            self.current_work.cancel()

        return anything

    def do_real_work(self):
        """
        Actually do the work, then add the appropriate callbacks, store info,
        etc.  Note: this particular ordering of operations is important.
        """
        self.delayed_call = None   # because work will be called

        # self.current_work might be set to None on the next line since the
        # deferred returned by do_work may have already fired.  So must be able
        # to refer to it by some other name.
        self.current_work = work_d = defer.maybeDeferred(self.do_work)

        # work is done - no need to cancel operations
        work_d.addBoth(self.clear_current_work)
        # propagate the success
        work_d.addCallback(self.deferred.callback)
        # After this - only error cases.  Figure out if it is terminal first.
        # If so, propagate to self.deferred
        work_d.addErrback(self.handle_failure)
        work_d.addErrback(self.deferred.errback)

    def start(self):
        """
        Kick the whole thing off by calling ``do_real_work``, and return
        ``self.deferred``
        """
        self.do_real_work()
        return self.deferred


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
        the number of seconds until the next attempt as a float.  Should be
        synchronous.

    :return: a Deferred which fires with the result of the ``do_work``,
        if successful, or the failure of the ``do_work``, if cannot be retried
    """
    retrier = _Retrier(do_work, can_retry, next_interval, clock)
    return retrier.start()
