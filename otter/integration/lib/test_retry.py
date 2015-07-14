"""
Tests for retrying treq.
"""
from twisted.internet.defer import fail, inlineCallbacks, returnValue, succeed
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from twisted.web.client import ResponseFailed

from otter.integration.lib.retry import RetryingTreq, retry
from otter.integration.lib.test_nova import Response
from otter.util.deferredutils import TimedOutError
from otter.util.retry import TransientRetryError


class FakeTreq(object):
    """
    Fake treq object
    """
    def __init__(self, responses):
        """Store a list of responses"""
        self._responses = responses

    def get(self, *args, **kwargs):
        """Return the next response"""
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            return fail(r)
        return succeed(r)

    def content(self, response):
        """Get the response content"""
        return succeed(response.strbody)


class RetryingTreqTests(TestCase):
    """
    Tests for a trial that retries.
    """
    def test_retrying_treq_retries_until_request_success(self):
        """
        Retrying-treq retries on over-limit errors and connection failed errors
        until it succeeds
        """
        clock = Clock()
        treq = FakeTreq([ResponseFailed(Failure(Exception('boo'))),
                         Response(413, {}, '{"overLimit": {}}'),
                         Response(413, {}, 'non-over-limit-response')])

        rtreq = RetryingTreq(treq=treq, clock=clock, timeout=5, period=1)

        d = rtreq.get("http://someurl.com")
        self.assertNoResult(d)  # ResponseFailed
        clock.pump([1])
        self.assertNoResult(d)  # 413 over limit
        clock.pump([1])
        r = self.successResultOf(d)
        self.assertEqual(r.code, 413)
        self.assertEqual(self.successResultOf(rtreq.content(r)),
                         'non-over-limit-response')

    def test_retrying_treq_retries_until_timeout(self):
        """
        Retrying-treq will retry until timeout.
        """
        clock = Clock()
        treq = FakeTreq([ResponseFailed(Failure(Exception('boo')))] * 5)
        rtreq = RetryingTreq(treq=treq, clock=clock, timeout=5, period=1)

        d = rtreq.get("http://someurl.com")
        self.assertNoResult(d)
        clock.pump([1] * 5)
        self.failureResultOf(d, TimedOutError)

    def test_retrying_bails_on_any_other_error(self):
        """
        If an error is raised by treq that is not a :obj:`ResponseFailed`
        error, retries stop.
        """
        clock = Clock()
        treq = FakeTreq([ValueError('meh')])
        rtreq = RetryingTreq(treq=treq, clock=clock, timeout=5, period=1)

        d = rtreq.get("http://someurl.com")
        self.failureResultOf(d, ValueError)

    def test_compose_retrying_treq_with_retry_no_outer_retry(self):
        """
        Using retrying treq with another retry layer - the outer retry will
        actually never retry if retrying-treq never returns.
        """
        clock = Clock()
        treq = FakeTreq([ResponseFailed(Failure(Exception('boo')))] * 5)
        rtreq = RetryingTreq(treq=treq, clock=clock, timeout=30, period=1)

        @retry("Test case", timeout=5, period=1, clock=clock)
        @inlineCallbacks
        def use_retrying_treq():
            yield rtreq.get("http://someurl.com")
            self.fail("Should never have gotten to this point")

        d = use_retrying_treq()
        self.assertNoResult(d)
        clock.pump([1] * 5)
        self.failureResultOf(d, TimedOutError)

    def test_compose_retrying_treq_with_retry_with_outer_retry(self):
        """
        Using retrying treq with another retry layer - the outer retry will
        retry if retrying-treq returns.
        """
        clock = Clock()
        treq = FakeTreq([ResponseFailed(Failure(Exception('boo'))),
                         Response(400, {}, 'not ok'),
                         ResponseFailed(Failure(Exception('boo'))),
                         Response(200, {}, 'ok')])
        rtreq = RetryingTreq(treq=treq, clock=clock, timeout=30, period=1)

        @retry("Test case", timeout=5, period=1, clock=clock)
        @inlineCallbacks
        def use_retrying_treq():
            r = yield rtreq.get("http://someurl.com")
            if r.code != 200:
                raise TransientRetryError()
            returnValue(r)

        d = use_retrying_treq()
        self.assertNoResult(d)
        clock.pump([1] * 5)
        r = self.successResultOf(d)
        self.assertEqual(r.code, 200)
        self.assertEqual(self.successResultOf(rtreq.content(r)), 'ok')
