"""
Module that provides retrying-at-a-particular-interval functionality.
"""

import random

from characteristic import Attribute, attributes

from effect import Delay, Effect, Func, sync_performer
from effect.retry import retry as effect_retry

from twisted.internet import defer
from twisted.python.failure import Failure


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

        self.deferred = defer.Deferred(self.handle_cancellation)

        self.current_work = None
        self.delayed_call = None
        self.cancelled = False

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
        if self.cancelled:
            raise defer.CancelledError

        if not self.can_retry(f):
            return f

        self.delayed_call = self.clock.callLater(self.next_interval(f),
                                                 self.do_real_work)

    def handle_cancellation(self, _deferred):
        """
        If ``self.deferred`` is cancelled, then the work already in progress
        and scheduled needs to be cancelled.
        """
        self.cancelled = True

        if self.delayed_call is not None:
            self.delayed_call.cancel()

        if self.current_work is not None:
            self.current_work.cancel()

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

    def stop(self):
        """
        Stop retrying by cancelling next schedule but will not disturb currently
        running operation. Use start()'s deferred.cancel() to stop retrying and stop
        currently running operation
        """
        self.cancelled = True
        if self.delayed_call is not None:
            self.delayed_call.cancel()


def transient_errors_except(*args):
    """
    Returns a ``can_retry`` function for :py:func:retry` that ignores all
    errors as transient except the ``Exception`` types specified.

    :return: a function that accepts a :class:`Failure` and returns ``True``
        only if the :class:`Failure` does not wrap an Exception passed in the
        args.  If no args are passed, all :class:`Exception`s are treated as
        transient.
    """
    def can_retry(f):
        return not f.check(*args)

    return can_retry


def terminal_errors_except(*args):
    """
    Returns a ``can_retry`` function for :py:func:retry` that only retries if
    errors the ``Exception`` types specified.

    :return: a function that accepts a :class:`Failure` and returns ``True``
        only if the :class:`Failure` wraps an Exception passed in the args.
        If no args are passed, no :class:`Exception` is treated as transient.
    """
    def can_retry(f):
        return f.check(*args)

    return can_retry


def retry_times(max_tries):
    """
    Returns a ``can_retry`` function for :py:func:retry` that ignores all
    errors and returns True until it has been called `max_tries` number of times

    :return: a function that accepts a :class:`Failure` and returns ``True``
        until it has been called ``max_tries`` times. Otherwise, returns ``False``
    """
    return RetryTimes(max_retries=max_tries)


def compose_retries(*can_retry_funcs):
    """
    Compose other can_retry functions into a single function that calls each
    of the passed can_retry function in the sequence and returns True only if all
    of them return True

    :return: a function that accepts a :class:`Failure` and returns ``True``
        only if all `can_retry_funcs` return True on that failure.
        Otherwise, returns ``False``
    """
    def can_retry(f):
        for func in can_retry_funcs:
            if not func(f):
                return False
        return True

    return can_retry


def repeating_interval(interval):
    """
    Returns a ``can_retry`` function for :py:func:retry` that returns the
    specified interval all the time.

    :return: a function that accepts a :class:`Failure` and returns ``interval``
    """
    return lambda f: interval


def random_interval(minimum, maximum):
    """
    Returns a ``can_retry`` function for :py:func:retry` that returns different
    random interval between `minimum` and `maximum` each time it is called

    :return: a function that accepts a :class:`Failure` and returns ``interval``
    """
    return lambda f: random.uniform(minimum, maximum)


def exponential_backoff_interval(start=2):
    """
    Returns a ``next_interval`` function for `:py:func:retry` that returns previous
    interval * 2 as new interval each time it is called

    :param start: number of seconds > 0 to start with
    :return: a function that accepts a :class:`Failure` and returns ``interval``
    """
    return ExponentialBackoffInterval(start=start)


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
        if all retries should be aborted.  Should be synchronous.  If None,
        defaults to something that treats all errors as transient.  Some
        default functions that can be used are, for instance,
        :func:`transient_errors_except`.

    :param callable next_interval: function that takes a failure and returns
        the number of seconds until the next attempt as a float.  Should be
        synchronous.  If None, defaults to something that always returns a 5
        second interval.  Some default functions that can be used are, for
        instance, :func:`repeating_interval`.

    :return: a Deferred which fires with the result of the ``do_work``,
        if successful, or the failure of the ``do_work``, if cannot be retried
    """
    if can_retry is None:
        can_retry = transient_errors_except()

    if next_interval is None:
        next_interval = repeating_interval(5)

    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    retrier = _Retrier(do_work, can_retry, next_interval, clock)
    return retrier.start()


class TransientRetryError(Exception):
    """
    Exception that can be used to represent retry-able status in a
    retry-function.
    """


# TODO: The following code should be moved to effect.retry if it proves out.

@attributes(['start', Attribute('last_interval', default_value=0)])
class ExponentialBackoffInterval(object):
    """
    A callable that returns the previous interval * 2 (starting at
    ``start``) every time it's called.

    :param start: number of seconds > 0 to start with
    :return: a function that accepts a :class:`Failure` and returns ``interval``
    """

    def __call__(self, failure):
        """Return an increasingly larger number."""
        if self.last_interval != 0:
            self.last_interval *= 2
        else:
            self.last_interval = self.start
        return self.last_interval


@attributes(['max_retries', Attribute('tries', default_value=0)])
class RetryTimes(object):
    """
    A callable that returns True until it's been called ``max_retries``.
    :param max_retries: Number of times to return True.
    """
    def __call__(self, failure):
        """Return True if this has been called <= ``max_retries``."""
        self.tries += 1
        return self.tries <= self.max_retries


@attributes(['can_retry', 'next_interval'])
class ShouldDelayAndRetry(object):
    """
    A callable which can be passed as the should_retry argument to
    :func:`effect.retry.retry`. Determines whether to retry and also causes
    a delay before retrying.

    :param can_retry: A callable of Failure -> Bool, indicating whether retry
        should occur
    :param next_interval: A callable of Failure -> interval to wait
    """

    def __call__(self, exc_info):
        """
        Determine whether retry should occur, based on the exception info.
        """
        exc_type, exc_value, exc_traceback = exc_info
        failure = Failure(exc_value, exc_type, exc_traceback)

        def doit():
            if self.can_retry(failure):
                interval = self.next_interval(failure)
                return Effect(Delay(interval)).on(lambda r: True)
            else:
                return False
        return Effect(Func(doit))


@attributes(['effect', 'should_retry'])
class Retry(object):
    """
    An effect intent that, when performed, executes another effect and
    potentially retries it.

    The main reason this class exists is to transparently represent the
    retryable effect and its retry policy as public attributes, making it
    easy to test that some effect should be retried, without actually running
    a bunch of imperative code to test it's retried correctly.

    :param effect: The effect to perform.
    :param should_retry: The function to call to determine whether retry
    should occur (usually an instance of :obj:`ShouldDelayAndRetry`).
    """


@sync_performer
def perform_retry(dispatcher, intent):
    """
    Invoke :func:`effect.retry.retry` with the effect and the
    should_retry function.
    """
    return effect_retry(intent.effect, intent.should_retry)


def retry_effect(effect, can_retry, next_interval):
    """
    Convenience function for wrapping an effect in a :obj:`Retry`.

    :return: :obj:`Effect` of :obj:`Retry`.
    """
    return Effect(Retry(
        effect=effect,
        should_retry=ShouldDelayAndRetry(can_retry=can_retry,
                                         next_interval=next_interval)))
