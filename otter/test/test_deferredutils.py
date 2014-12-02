"""
Tests for `otter.utils.deferredutils`
"""
import mock

from twisted.internet.task import Clock
from twisted.internet.defer import CancelledError, Deferred
from twisted.trial.unittest import SynchronousTestCase

from otter.util.deferredutils import (
    timeout_deferred, retry_and_timeout, TimedOutError, DeferredPool, wait)
from otter.test.utils import DummyException, patch


class TimeoutDeferredTests(SynchronousTestCase):
    """
    Tests for the method method ``timeout_deferred``
    """
    def setUp(self):
        """
        Create a clock and a deferred to be cancelled
        """
        self.clock = Clock()
        self.deferred = Deferred()

    def test_propagates_result_if_success_before_timeout(self):
        """
        The deferred callbacks with the result if it succeeds before the
        timeout (e.g. timing out the deferred does not obscure the callback
        value).
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 10, clock)
        d.callback("Result")
        self.assertEqual(self.successResultOf(d), "Result")

        # the timeout never happens - no errback occurs
        clock.advance(15)
        self.assertIsNone(self.successResultOf(d))

    def test_propagates_failure_if_failed_before_timeout(self):
        """
        The deferred errbacks with the failure if it fails before the
        timeout (e.g. timing out the deferred does not obscure the errback
        failure).
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 10, clock)
        d.errback(DummyException("fail"))
        self.failureResultOf(d, DummyException)

        # the timeout never happens - no further errback occurs
        clock.advance(15)
        self.assertIsNone(self.successResultOf(d))

    def test_times_out_if_past_timeout(self):
        """
        The deferred errbacks with a TimedOutError if the timeout occurs
        before it either callbacks or errbacks.
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.failureResultOf(d, TimedOutError)

    def test_preserves_cancellation_function_callback(self):
        """
        If a cancellation function that callbacks is provided to the deferred
        being cancelled, its effects will not be overriden with a TimedOutError.
        """
        d = Deferred(lambda c: c.callback('I was cancelled!'))
        timeout_deferred(d, 10, self.clock)
        self.assertNoResult(d)

        self.clock.advance(15)

        self.assertEqual(self.successResultOf(d), 'I was cancelled!')

    def test_preserves_cancellation_function_errback(self):
        """
        If a cancellation function that errbacks (with a non-CancelledError) is
        provided to the deferred being cancelled, this other error will not be
        converted to a TimedOutError.
        """
        d = Deferred(lambda c: c.errback(DummyException('what!')))
        timeout_deferred(d, 10, self.clock)
        self.assertNoResult(d)

        self.clock.advance(15)

        self.failureResultOf(d, DummyException)

    def test_preserves_early_cancellation_error(self):
        """
        If the Deferred is manually cancelled before the timeout, it is not
        re-cancelled (no AlreadyCancelledError), and the CancelledError is not
        obscured
        """
        timeout_deferred(self.deferred, 10, self.clock)
        self.assertNoResult(self.deferred)

        self.deferred.cancel()
        self.failureResultOf(self.deferred, CancelledError)

        self.clock.advance(15)
        # no AlreadyCancelledError raised?  Good.

    def test_deferred_description_passed_to_TimedOutError(self):
        """
        If a deferred_description is passed, the TimedOutError will have that
        string as part of it's string representation.
        """
        timeout_deferred(self.deferred, 5.3, self.clock,
                         deferred_description="It'sa ME!")
        self.clock.advance(6)

        f = self.failureResultOf(self.deferred, TimedOutError)
        self.assertIn("It'sa ME! timed out after 5.3 seconds", str(f))


class RetryAndTimeoutTests(SynchronousTestCase):
    """
    Tests for ``retry_and_timeout``.  Since this is just a composition of two
    already tested functions, just ensure that the arguments passed
    get propagated correctly to the respective functions.
    """
    def setUp(self):
        """
        Patch both retry and timeout
        """
        self.retry = patch(self, 'otter.util.deferredutils.retry')
        self.timeout = patch(self, 'otter.util.deferredutils.timeout_deferred')

    def test_both_called_with_all_args(self):
        """
        Both ``retry`` and ``timeout`` gets called with the args passed to
        ``retry_and_timeout``, including the same clock
        """
        clock = mock.MagicMock()
        retry_and_timeout('do_work', 'timeout', can_retry='can_retry',
                          next_interval='next_interval', clock=clock,
                          deferred_description='description')

        self.retry.assert_called_once_with('do_work', can_retry='can_retry',
                                           next_interval='next_interval',
                                           clock=clock)
        self.timeout.assert_called_once_with(self.retry.return_value,
                                             'timeout', clock=clock,
                                             deferred_description='description')

    def test_retry_and_timeout_get_the_same_default_clock(self):
        """
        If no clock is passed to ``retry_and_timeout``, both ``retry`` and
        ``timeout`` nevertheless get the same clock.
        """
        retry_and_timeout('do_work', 'timeout')

        retry_clock = self.retry.call_args[1]['clock']
        timeout_clock = self.timeout.call_args[1]['clock']

        self.assertIs(retry_clock, timeout_clock)


class DeferredPoolTests(SynchronousTestCase):
    """
    Tests for :class:`DeferredPool`
    """
    def setUp(self):
        """
        Default DeferredPool for each case
        """
        self.pool = DeferredPool()

    def test_notify_when_empty_happens_immediately(self):
        """
        When ``notify_when_empty`` is called, if the pool is empty, the
        deferred returned callbacks immediately.
        """
        d = self.pool.notify_when_empty()
        self.successResultOf(d)

    def test_notify_when_empty_does_not_callback_previous_waiting(self):
        """
        The second time ``notify_when_empty`` is called, it only callback the
        deferreds that were created after the first call.
        """
        d1 = self.pool.notify_when_empty()
        self.successResultOf(d1)

        d2 = self.pool.notify_when_empty()
        self.successResultOf(d2)
        # no AlreadyCalledError?

    def test_notify_does_not_notify_until_pooled_deferreds_callback(self):
        """
        If there are one or more deferreds in the pool, ``notify_when_empty``
        does not notify until they are callbacked.
        """
        holdup = Deferred()
        self.pool.add(holdup)

        d = self.pool.notify_when_empty()
        self.assertNoResult(d)

        holdup.callback('done')
        self.successResultOf(d)

    def test_notify_does_not_notify_until_pooled_deferreds_errbacks(self):
        """
        If there are one or more deferreds in the pool, ``notify_when_empty``
        does not notify until they are fired - works with errbacks too.
        """
        holdup = Deferred()
        self.pool.add(holdup)

        d = self.pool.notify_when_empty()
        self.assertNoResult(d)

        holdup.errback(DummyException('hey'))
        self.successResultOf(d)

        # don't leave unhandled Deferred lying around
        self.failureResultOf(holdup)

    def test_notify_when_empty_notifies_all_waiting(self):
        """
        All waiting Deferreds resulting from previous calls to
        ``notify_when_empty`` will callback as soon as the pool is empty.
        """
        holdup = Deferred()
        self.pool.add(holdup)

        previous = [self.pool.notify_when_empty() for i in range(5)]
        for d in previous:
            self.assertNoResult(d)

        holdup.callback('done')

        for d in previous:
            self.successResultOf(d)

    def test_pooled_deferred_callbacks_not_obscured(self):
        """
        The callbacks of pooled deferreds are not obscured by removing them
        from the pool.
        """
        holdup = Deferred()
        self.pool.add(holdup)
        holdup.callback('done')
        self.assertEqual(self.successResultOf(holdup), 'done')

    def test_pooled_deferred_errbbacks_not_obscured(self):
        """
        The errbacks of pooled deferreds are not obscured by removing them
        from the pool.
        """
        holdup = Deferred()
        self.pool.add(holdup)
        holdup.errback(DummyException('hey'))
        self.failureResultOf(holdup, DummyException)

    def test_len(self):
        """
        len(pool) returns number of deferreds waiting in the pool
        """
        self.assertEqual(len(self.pool), 0)
        d = Deferred()
        self.pool.add(d)
        self.assertEqual(len(self.pool), 1)
        d.callback(None)
        self.assertEqual(len(self.pool), 0)


class WaitTests(SynchronousTestCase):
    """
    Tests for :func:`wait`
    """

    def setUp(self):
        """
        Sample function being decorated
        """

        @wait()
        def f(n):
            return self.returns.pop(0)

        self.f = f

    def _test_success_waits(self):
        self.returns = [Deferred()]
        fd = self.returns[0]
        d1 = self.f(1)
        d2 = self.f(1)
        d3 = self.f(1)
        # Actual f called only once otherwise f would've errored
        self.assertIs(fd, d1)
        self.assertNoResult(d2)
        self.assertNoResult(d3)
        fd.callback(2)
        self.assertEqual(self.successResultOf(d2), 2)
        self.assertEqual(self.successResultOf(d3), 2)

    def test_success_waits(self):
        """
        Calling decorated function again with same arg calls wrapped function only once
        and returns result to all callers
        """
        self._test_success_waits()

    def test_success_waits_again(self):
        """
        Calling decorated function again after previous wait has completed calls
        wrapped function again
        """
        self._test_success_waits()
        self.assertEqual(self.returns, [])
        self._test_success_waits()

    def test_success_diff_args(self):
        """
        Calling decorated function again with diff arg calls wrapped function only once
        for specific argument
        """
        self.returns = [Deferred(), Deferred()]
        a1d, a2d = self.returns
        d11 = self.f(1)
        d12 = self.f(1)
        d2 = self.f(2)
        self.assertIs(a1d, d11)
        a1d.callback(3)
        self.assertEqual(self.successResultOf(d12), 3)
        self.assertNoResult(d2)
        a2d.callback(4)
        self.assertEqual(self.successResultOf(d2), 4)

    def test_err_waits(self):
        """
        Calling decorated function again with same arg calls wrapped function only once
        and errors to all callers if original call errors
        """
        self.returns = [Deferred()]
        fd = self.returns[0]
        d1 = self.f(1)
        d2 = self.f(1)
        d3 = self.f(1)
        # Actual f called only once otherwise f would've errored
        self.assertIs(fd, d1)
        self.assertNoResult(d2)
        self.assertNoResult(d3)
        fd.errback(ValueError('oops'))
        self.failureResultOf(d2, ValueError)
        self.failureResultOf(d3, ValueError)
        self.failureResultOf(fd)  # Clear error

    def test_err_diff_args(self):
        """
        Calling decorated function again with diff arg calls wrapped function only once
        for specific argument and returns result to all callers from original call
        """
        self.returns = [Deferred(), Deferred()]
        a1d, a2d = self.returns
        d11 = self.f(1)
        d12 = self.f(1)
        d2 = self.f(2)
        self.assertIs(a1d, d11)
        a1d.errback(ValueError('a'))
        self.failureResultOf(d12, ValueError)
        self.failureResultOf(a1d)  # Clear error
        self.assertNoResult(d2)  # Deferred w.r.t 2 is not fired yet
        a2d.errback(NotImplementedError('a'))
        self.failureResultOf(d2, NotImplementedError)

    def test_with_kwargs(self):
        """
        If function is decorated by considering keyword arguments, then multiple
        calls to decorated function with same args is called only once
        """

        @wait(ignore_kwargs=False)
        def f(n, k=None):
            return self.returns.pop(0)

        self.returns = [Deferred(), Deferred()]
        fd = self.returns[0]
        d1 = f(1, k=11)
        d2 = f(1, k=11)
        d3 = f(1, k=15)
        fd.callback('r')
        self.assertEqual(self.successResultOf(d1), 'r')
        self.assertEqual(self.successResultOf(d2), 'r')
        self.assertNoResult(d3)
        d3.callback('a')
        self.assertEqual(self.successResultOf(d3), 'a')
