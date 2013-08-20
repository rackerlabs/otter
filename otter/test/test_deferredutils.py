"""
Tests for `otter.utils.deferredutils`
"""
from twisted.internet.task import Clock
from twisted.internet.defer import CancelledError, Deferred
from twisted.trial.unittest import TestCase

from otter.util.deferredutils import timeout_deferred
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
