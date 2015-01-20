"""
Tests for :mod:`otter.utils.retry`
"""
import sys

from effect import (
    ComposedDispatcher, Constant, Delay, Effect, Func, TypeDispatcher,
    base_dispatcher, sync_perform)
from effect.testing import Stub, resolve_effect

import mock

from twisted.internet.task import Clock
from twisted.internet.defer import CancelledError, Deferred, succeed
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from otter.test.utils import (
    CheckFailure, CheckFailureValue, DummyException)
from otter.util.retry import (
    Retry,
    ShouldDelayAndRetry,
    compose_retries,
    exponential_backoff_interval,
    perform_retry,
    random_interval,
    repeating_interval,
    retry,
    retry_effect,
    retry_times,
    terminal_errors_except,
    transient_errors_except,
)


class RetryTests(SynchronousTestCase):
    """
    Tests for the helper method method ``retry``
    """
    def setUp(self):
        """
        Set up a function to be used for retrying
        """
        self.retries = []

        def work_function():
            d = Deferred()
            wrapped = mock.MagicMock(spec=d, wraps=d)
            self.retries.append(wrapped)
            return wrapped

        self.clock = Clock()
        self.interval = 1
        self.interval_function = lambda *args: self.interval
        self.retry_function = lambda *args: True
        self.work_function = work_function

    def test_async_propagates_result_and_stops_retries_on_callback(self):
        """
        The deferred callbacks with the result as soon as the asynchronous
        ``do_work`` function succeeds.  No retries happen
        """
        d = retry(self.work_function, self.retry_function,
                  self.interval_function, self.clock)

        # no result until the work_function's deferred fires
        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        self.retries[-1].callback('result!')
        self.assertEqual(self.successResultOf(d), 'result!')

        # work_function not called again.
        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_sync_propagates_result_and_stops_retries_on_callback(self):
        """
        The deferred callbacks with the result as soon as the synchronous
        ``do_work`` function succeeds.  No retries happen
        """
        self.work_function = mock.MagicMock(spec=[], return_value='result!')
        d = retry(self.work_function, self.retry_function,
                  self.interval_function, self.clock)
        self.assertEqual(self.successResultOf(d), 'result!')
        self.work_function.assert_called_once_with()

        # work_function not called again.
        self.clock.advance(self.interval)
        self.work_function.assert_called_once_with()

    def test_ignores_transient_failures_and_retries(self):
        """
        Retries after interval if the ``do_work`` function errbacks with an
        error that is ignored by the ``can_retry`` function.  The error is
        not propagated.
        """
        wrapped_retry = mock.MagicMock(wraps=self.retry_function, spec=[])
        d = retry(self.work_function, wrapped_retry,
                  self.interval_function, self.clock)

        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        # no result on errback
        self.retries[-1].errback(DummyException('hey!'))
        self.assertIsNone(self.successResultOf(self.retries[-1]))
        self.assertNoResult(d)
        wrapped_retry.assert_called_once_with(CheckFailure(DummyException))

        self.clock.advance(self.interval)

        # since it was an errback, loop retries the function again
        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 2)

        # stop loop
        self.retries[-1].callback('result!')
        self.assertEqual(self.successResultOf(d), 'result!')

    def test_retries_at_intervals_specified_by_interval_function(self):
        """
        ``do_work``, if it experiences transient failures, will be retried at
        intervals returned by the ``next_interval`` function
        """
        changing_interval = mock.MagicMock(spec=[])
        d = retry(self.work_function, self.retry_function,
                  changing_interval, self.clock)

        changing_interval.return_value = 1
        self.assertEqual(len(self.retries), 1)
        self.retries[-1].errback(DummyException('hey!'))
        self.assertNoResult(d)
        changing_interval.assert_called_once_with(CheckFailure(DummyException))

        self.clock.advance(1)
        changing_interval.return_value = 2
        self.assertEqual(len(self.retries), 2)
        self.retries[-1].errback(DummyException('hey!'))
        self.assertNoResult(d)
        changing_interval.assert_has_calls(
            [mock.call(CheckFailure(DummyException))] * 2)

        # the next interval has changed - after 1 second, it is still not
        # retried
        self.clock.advance(1)
        self.assertEqual(len(self.retries), 2)
        self.assertNoResult(d)
        changing_interval.assert_has_calls(
            [mock.call(CheckFailure(DummyException))] * 2)

        # after 2 seconds, the function is retried
        self.clock.advance(1)
        self.assertEqual(len(self.retries), 3)

        # stop retrying
        self.retries[-1].callback('hey')

    def test_stops_on_non_transient_error(self):
        """
        If ``do_work`` errbacks with something the ``can_retry`` function does
        not ignore, the error is propagated up.  ``do_work`` is not retried.
        """
        d = retry(self.work_function, lambda *args: False,
                  self.interval_function, self.clock)

        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        self.retries[-1].errback(DummyException('fail!'))
        self.failureResultOf(d, DummyException)

        # work_function not called again
        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_handles_synchronous_do_work_function_errors(self):
        """
        Transient/terminal error handling works the same with a synchronous
        ``do_work`` function that raises instead of errbacks.
        """
        self.work_function = mock.MagicMock(spec=[])
        self.work_function.side_effect = DummyException

        # DummyExceptions are transient, all else are terminal
        d = retry(self.work_function, (lambda f: f.check(DummyException)),
                  self.interval_function, self.clock)

        # no result
        self.assertNoResult(d)
        self.work_function.assert_called_once_with()

        self.work_function.side_effect = NotImplementedError
        self.clock.advance(self.interval)

        # terminal error
        self.failureResultOf(d, NotImplementedError)
        self.assertEqual(self.work_function.call_count, 2)

    def test_cancelling_deferred_cancels_work_in_progress(self):
        """
        Cancelling the deferred cancels the deferred returned by
        ``do_work`` if it is still in progress, but eats the
        :class:`CancelledError` (but the overall retry deferred still
        errbacks with a :class:`CancelledError`)
        """
        d = retry(self.work_function, self.retry_function,
                  self.interval_function, self.clock)
        self.assertEqual(len(self.retries), 1)
        self.assertNoResult(self.retries[-1])

        # cancel main deferred
        d.cancel()
        self.failureResultOf(d, CancelledError)

        # work_function's deferred is cancelled, and error eaten
        self.retries[-1].cancel.assert_called_once_with()
        self.assertIsNone(self.successResultOf(self.retries[-1]))

    def test_cancelling_deferred_does_not_cancel_completed_work(self):
        """
        Cancelling the deferred does not attempt to cancel previously
        callbacked results from ``do_work``
        """
        d = retry(self.work_function, self.retry_function,
                  self.interval_function, self.clock)

        self.assertEqual(len(self.retries), 1)
        self.retries[-1].errback(DummyException('temp'))

        # cancel main deferred
        d.cancel()
        self.failureResultOf(d, CancelledError)

        # work_function's deferred is not cancelled
        self.assertEqual(self.retries[-1].cancel.call_count, 0)
        self.assertIsNone(self.successResultOf(self.retries[-1]))

    def test_cancelling_deferred_stops_retries(self):
        """
        Cancelling the deferred prevents ``retry`` from retrying ``do_work``
        again.
        """
        d = retry(self.work_function, self.retry_function,
                  self.interval_function, self.clock)
        self.assertEqual(len(self.retries), 1)

        d.cancel()
        self.failureResultOf(d, CancelledError)

        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_already_callbacked_deferred_not_canceled(self):
        """
        If ``do_work``'s deferred has already fired, ``retry``
        callbacks correctly without canceling the fired deferred.
        """
        r = succeed('result!')
        wrapped = mock.MagicMock(spec=r, wraps=r)
        work_function = mock.MagicMock(spec=[], return_value=wrapped)

        d = retry(work_function, self.retry_function,
                  self.interval_function, self.clock)
        self.assertEqual(self.successResultOf(d), 'result!')

        self.assertEqual(wrapped.cancel.call_count, 0)

    def test_default_can_retry_function(self):
        """
        If no ``can_retry`` function is provided, a default function treats
        any failure as transient
        """
        d = retry(self.work_function, None, self.interval_function, self.clock)

        self.assertEqual(len(self.retries), 1)
        self.retries[-1].errback(DummyException('temp'))

        self.clock.advance(self.interval)

        self.assertEqual(len(self.retries), 2)
        self.retries[-1].errback(NotImplementedError())

        self.assertNoResult(d)

    def test_default_next_interval_function(self):
        """
        If no ``next_interval`` function is provided, a default function returns
        5 no matter what the failure.
        """
        d = retry(self.work_function, self.retry_function, None, self.clock)

        self.assertEqual(len(self.retries), 1)
        self.retries[-1].errback(DummyException('temp'))

        self.clock.advance(5)

        self.assertEqual(len(self.retries), 2)
        self.retries[-1].errback(NotImplementedError())

        self.clock.advance(5)

        self.assertEqual(len(self.retries), 3)
        self.assertNoResult(d)


class CanRetryHelperTests(SynchronousTestCase):
    """
    Tests for ``can_retry`` implementations such as ``transient_errors_except``
    """

    def test_transient_errors_except_defaults_to_all_transient(self):
        """
        If no args are provided to :func:`transient_errors_except`, the
        function it returns treats all errors as transient (returns True)
        """
        can_retry = transient_errors_except()

        for exception in (DummyException(), NotImplementedError()):
            self.assertTrue(can_retry(Failure(exception)))

    def test_transient_errors_except_terminates_on_provided_exceptions(self):
        """
        If the failure is of a type provided to :func:`transient_errors_except`,
        the function it returns will treat it as terminal (returns False)
        """
        can_retry = transient_errors_except(DummyException)
        self.assertFalse(can_retry(Failure(DummyException())))

    def test_retry_times(self):
        """
        `retry_times` returns function that will retry given number of times
        """
        can_retry = retry_times(3)
        for exception in (DummyException(), NotImplementedError(), ValueError()):
            self.assertTrue(can_retry(Failure(exception)))
        self.assertFalse(can_retry(Failure(DummyException())))

    def test_compose_retries(self):
        """
        `compose_retries` returns True only if all its function returns True
        """
        f1 = lambda f: f % 2 == 0
        f2 = lambda f: f % 5 == 0
        can_retry = compose_retries(f1, f2)
        # True only if both f1 and f2 return True
        self.assertTrue(can_retry(10))
        # False otherwise
        self.assertFalse(can_retry(8))
        self.assertFalse(can_retry(3))

    def test_terminal_errors_except_defaults_to_all_errors_bad(self):
        """
        If no args are provided to :func:`fail_unless`, the
        function it returns treats all errors as terminal (returns False)
        """
        can_retry = terminal_errors_except()

        for exception in (DummyException(), NotImplementedError()):
            self.assertFalse(can_retry(Failure(exception)))

    def test_terminal_errors_except_continues_on_provided_exceptions(self):
        """
        If the failure is of a type provided to :func:`transient_errors_except`,
        the function it returns will treat it as transient (returns True)
        """
        can_retry = terminal_errors_except(DummyException)
        self.assertTrue(can_retry(Failure(DummyException())))


class NextIntervalHelperTests(SynchronousTestCase):
    """
    Tests for ``next_interval`` implementations such as ``repeating_interval``
    """

    def test_repeating_interval_always_returns_interval(self):
        """
        ``repeating_interval`` returns the same interval no matter what the
        failure
        """
        next_interval = repeating_interval(3)
        for exception in (DummyException(), NotImplementedError()):
            self.assertEqual(next_interval(Failure(exception)), 3)

    def test_random_interval(self):
        """
        ``random_interval`` returns the different random interval each time it
        is called
        """
        next_interval = random_interval(5, 10)
        intervals = set()
        for exception in [DummyException(), NotImplementedError(), ValueError(),
                          FloatingPointError(), IOError()]:
            interval = next_interval(exception)
            self.assertTrue(5 <= interval <= 10)
            self.assertNotIn(interval, intervals)
            intervals.add(interval)

    def test_exp_backoff_interval(self):
        """
        ``exponential_backoff_interval`` returns previous interval * 2 every
        time it is called
        """
        err = DummyException()
        next_interval = exponential_backoff_interval(3)
        self.assertEqual(next_interval(err), 3)
        self.assertEqual(next_interval(err), 6)
        self.assertEqual(next_interval(err), 12)


STUB = Effect(Stub(Constant("foo")))


class RetryEffectTests(SynchronousTestCase):
    """Tests for :func:`retry_effect`."""

    def test_retry_effect(self):
        """
        :func:`retry_effect` takes an effect and returns an :obj:`Effect` of
        :obj:`Retry`, with a :obj:`ShouldDelayAndRetry` as the should_retry
        callable.
        """
        can_retry = lambda f: True
        next_interval = lambda f: 1
        eff = retry_effect(STUB, can_retry, next_interval)
        self.assertEqual(
            eff,
            Effect(Retry(
                effect=STUB,
                should_retry=ShouldDelayAndRetry(can_retry=can_retry,
                                                 next_interval=next_interval))))


def _raise(exc):
    raise exc


def _repeated_effect_func(*funcs):
    """
    Return an (impure) function which does different things based on the
    number of times it's been called.
    """
    counter = [0]

    def func():
        count = counter[0]
        counter[0] += 1
        return funcs[count]()

    return func


class EffectfulRetryTests(SynchronousTestCase):
    """Tests for :obj:`Retry`."""

    # Sadly, these are basically a less thorough version of effect.retry's
    # tests. How could this be improved? by generalizing the concept of
    # an object which calls a function with arguments specified as public
    # attributes, I guess...

    def setUp(self):
        """Save common objects."""
        self.dispatcher = ComposedDispatcher([
            base_dispatcher,
            TypeDispatcher({Retry: perform_retry})])

    def test_perform_retry(self):
        """
        When the specified effect is successful, its result is propagated.
        """
        retry = Retry(effect=Effect(Constant('foo')),
                      should_retry=lambda e: 1 / 0)
        result = sync_perform(self.dispatcher, Effect(retry))
        self.assertEqual(result, 'foo')

    def test_perform_retry_retries_on_error(self):
        """
        When the specified effect raises, it is retried when should_retry
        returns an Effect of True.
        """
        func = _repeated_effect_func(
            lambda: _raise(RuntimeError("foo")),
            lambda: "final")

        def should_retry(exc_info):
            if (exc_info[0] is RuntimeError
                    and exc_info[1].message == "foo"):
                return Effect(Constant(True))
            else:
                return Effect(Constant(False))

        retry = Retry(effect=Effect(Func(func)),
                      should_retry=should_retry)
        result = sync_perform(self.dispatcher, Effect(retry))
        self.assertEqual(result, "final")


def get_exc_info():
    """Get the exc_info tuple representing a ZeroDivisionError('foo')"""
    try:
        raise ZeroDivisionError("foo")
    except Exception:
        return sys.exc_info()


def _perform_func_intent(eff):
    """Perform a func intent without recursing on effects."""
    assert type(eff.intent) is Func
    return eff.intent.func()


class ShouldDelayAndRetryTests(SynchronousTestCase):
    """Tests for :obj:`ShouldDelayAndRetry`."""

    def test_should_not_retry(self):
        """
        When an instance is called, an Effect of False is returned if the
        can_retry function returns False.
        """
        sdar = ShouldDelayAndRetry(can_retry=lambda f: False,
                                   next_interval=lambda f: 1 / 0)
        eff = sdar(get_exc_info())
        self.assertEqual(_perform_func_intent(eff), False)

    def test_should_retry(self):
        """
        When called and can_retry returns True, a Delay based on next_interval
        is executed and the ultimate result is True.
        """
        sdar = ShouldDelayAndRetry(can_retry=lambda f: True,
                                   next_interval=lambda f: 1.5)
        eff = sdar(get_exc_info())
        next_eff = _perform_func_intent(eff)
        self.assertEqual(next_eff.intent, Delay(delay=1.5))
        self.assertEqual(resolve_effect(next_eff, None),
                         True)

    def test_failure_passed_correctly(self):
        """
        The failure argument to can_retry and next_interval represents the
        error that occurred.
        """
        can_retry_failures = []
        next_interval_failures = []

        def can_retry(failure):
            can_retry_failures.append(failure)
            return True

        def next_interval(failure):
            next_interval_failures.append(failure)
            return 0.5

        sdar = ShouldDelayAndRetry(can_retry=can_retry,
                                   next_interval=next_interval)
        eff = sdar(get_exc_info())
        _perform_func_intent(eff)
        self.assertEqual(can_retry_failures, next_interval_failures)
        self.assertEqual(can_retry_failures[0],
                         CheckFailureValue(ZeroDivisionError("foo")))
