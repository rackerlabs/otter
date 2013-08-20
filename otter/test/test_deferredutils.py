"""
Tests for `otter.utils.deferredutils`
"""
import mock

from twisted.internet.task import Clock
from twisted.internet.defer import (AlreadyCalledError, CancelledError,
                                    Deferred, succeed)
from twisted.trial.unittest import TestCase

from otter.util.deferredutils import timeout_deferred, retry
from otter.test.utils import CheckFailure, DummyException


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

        def work_function():
            d = Deferred()
            wrapped = mock.MagicMock(spec=d, wraps=d)
            self.retries.append(wrapped)
            return wrapped

        self.clock = Clock()
        self.interval = 5
        self.interval_function = lambda *args: self.interval
        self.retry_function = lambda *args: True
        self.work_function = work_function

    def test_propagates_result_and_stops_retries_on_callback(self):
        """
        The deferred callbacks with the result as soon as the ``do_work``
        function succeeds.  No retries happen
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
