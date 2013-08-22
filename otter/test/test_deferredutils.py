"""
Tests for `otter.utils.deferredutils`
"""
import mock

from twisted.internet.task import Clock
from twisted.internet.defer import CancelledError, Deferred
from twisted.trial.unittest import TestCase

from otter.util.deferredutils import (
    timeout_deferred, retry_and_timeout, TimedOutError)
from otter.test.utils import DummyException, patch


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
        clock = Clock()
        d = Deferred(lambda c: c.callback('I was cancelled!'))
        timeout_deferred(d, 10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.assertEqual(self.successResultOf(d), 'I was cancelled!')

    def test_preserves_cancellation_function_errback(self):
        """
        If a cancellation function that errbacks (with a non-CancelledError) is
        provided to the deferred being cancelled, this other error will not be
        converted to a TimedOutError.
        """
        clock = Clock()
        d = Deferred(lambda c: c.errback(DummyException('what!')))
        timeout_deferred(d, 10, clock)
        self.assertNoResult(d)

        clock.advance(15)

        self.failureResultOf(d, DummyException)

    def test_preserves_early_cancellation_error(self):
        """
        If the Deferred is manually cancelled before the timeout, it is not
        re-cancelled (no AlreadyCancelledError), and the CancelledError is not
        obscured
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 10, clock)
        self.assertNoResult(d)

        d.cancel()
        self.failureResultOf(d, CancelledError)

        clock.advance(15)
        # no AlreadyCancelledError raised?  Good.

    def test_deferred_description_passed_to_TimedOutError(self):
        """
        If a deferred_description is passed, the TimedOutError will have that
        string as part of it's string representation.
        """
        clock = Clock()
        d = Deferred()
        timeout_deferred(d, 5.3, clock, deferred_description="It'sa ME!")
        clock.advance(6)

        f = self.failureResultOf(d, TimedOutError)
        self.assertIn("It'sa ME! timed out after 5.3 seconds", str(f))


class RetryAndTimeoutTests(TestCase):
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
