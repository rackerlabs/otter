"""
Tests for `otter.utils.deferredutils`
"""
import mock

from twisted.internet.task import Clock
from twisted.internet.defer import CancelledError, Deferred, fail, succeed
from twisted.trial.unittest import TestCase

from otter.util.deferredutils import (
    timeout_deferred, retry, TransientRetryError, wrap_transient_error)
from otter.test.utils import DummyException


class TimeoutDeferredTests(TestCase):
    """
    Tests for the method method ``timeout_deferred``
    """
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

    def test_cancels_if_past_timeout(self):
        """
        The deferred errbacks with an CancelledError if the timeout occurs
        before it either callbacks or errbacks.
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.failureResultOf(d, CancelledError)


class RetryTests(TestCase):
    """
    Tests for the helper method method ``retry``
    """
    def setUp(self):
        """
        Set up a function to be used for retrying
        """
        self.retries = []

        def retry_function():
            d = Deferred()
            wrapped = mock.MagicMock(spec=d, wraps=d)
            self.retries.append(wrapped)
            return wrapped

        self.clock = Clock()
        self.interval = 5
        self.retry_function = retry_function

    def test_propagates_result_and_stops_loop_on_callback(self):
        """
        The deferred callbacks with the result as soon as the ``retry_function``
        succeeds.  Looping also stops.
        """
        d = retry(self.retry_function, self.interval, self.clock)

        # no result until the retry_function's deferred fires
        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        self.retries[-1].callback('result!')
        self.assertEqual(self.successResultOf(d), 'result!')

        # loop is stopped - retry_function not called again.
        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_ignores_transient_failures_and_retries(self):
        """
        Retries after interval if ``retry_function`` errbacks with a
        TransientRetryError, and said TransientRetryError is eaten.
        """
        d = retry(self.retry_function, self.interval, self.clock)

        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        # no result on errback
        self.retries[-1].errback(TransientRetryError('hey'))
        self.assertIsNone(self.successResultOf(self.retries[-1]))
        self.assertNoResult(d)

        self.clock.advance(self.interval)

        # since it was an errback, loop retries the function again
        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 2)

        # stop loop
        self.retries[-1].callback('result!')

    def test_stops_on_non_transient_error(self):
        """
        The deferred errbacks with whatever error the ``retry_function``
        errbacks with, if it is not a :class:`TransientRetryError`.  Looping
        also stops.
        """
        d = retry(self.retry_function, self.interval, self.clock)

        self.assertNoResult(d)
        self.assertEqual(len(self.retries), 1)

        self.retries[-1].errback(DummyException('fail!'))
        self.failureResultOf(d, DummyException)

        # loop is stopped - retry_function not called again.
        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_cancelling_deferred_cancels_work_in_progress(self):
        """
        Cancelling the deferred cancels the deferred returned by
        ``retry_function`` if it is still in progress, but eats the
        :class:`CancelledError` (but the overall retry deferred still
        errbacks with a :class:`CancelledError`)
        """
        d = retry(self.retry_function, self.interval, self.clock)
        self.assertEqual(len(self.retries), 1)
        self.assertNoResult(self.retries[-1])

        # cancel main deferred
        d.cancel()
        self.failureResultOf(d, CancelledError)

        # retry_function's deferred is cancelled, and error eaten
        self.retries[-1].cancel.assert_called_once_with()
        self.assertIsNone(self.successResultOf(self.retries[-1]))

    def test_cancelling_deferred_does_not_cancel_completed_work(self):
        """
        Cancelling the deferred does not attempt to cancel previously
        callbacked results from ``retry_function``
        """
        d = retry(self.retry_function, self.interval, self.clock)

        self.assertEqual(len(self.retries), 1)
        self.retries[-1].errback(TransientRetryError('temp'))

        # cancel main deferred
        d.cancel()
        self.failureResultOf(d, CancelledError)

        # retry_function's deferred is not cancelled
        self.assertEqual(self.retries[-1].cancel.call_count, 0)
        self.assertIsNone(self.successResultOf(self.retries[-1]))

    def test_cancelling_deferred_stops_loop(self):
        """
        Cancelling the deferred prevents the loop from retrying the function
        again.
        """
        d = retry(self.retry_function, self.interval, self.clock)
        self.assertEqual(len(self.retries), 1)

        d.cancel()
        self.failureResultOf(d, CancelledError)

        self.clock.advance(self.interval)
        self.assertEqual(len(self.retries), 1)

    def test_already_callbacked_deferred_not_canceled(self):
        """
        If the ``retry_function``'s deferred has already fired, ``retry``
        callbacks correctly without canceling the fired deferred.
        """
        r = succeed('result!')
        wrapped = mock.MagicMock(spec=r, wraps=r)
        retry_function = mock.MagicMock(spec=[], return_value=wrapped)

        d = retry(retry_function, self.interval, self.clock)
        self.assertEqual(self.successResultOf(d), 'result!')

        self.assertEqual(wrapped.cancel.call_count, 0)


class HelperFunctionTests(TestCase):
    """
    Tests for ``wrap_transient_error``
    """

    def test_wraps_original_failure(self):
        """
        ``wrap_transient_error`` wraps the original failure within a failure of
        type ``TransientRetryError``
        """
        d = fail(DummyException('hey'))
        d.addErrback(wrap_transient_error)

        f = self.failureResultOf(d, TransientRetryError)
        original = f.value.wrapped
        self.assertTrue(original.check(DummyException))
