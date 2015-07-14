"""
Module for retrying integration test utilities.
"""

from functools import partial, wraps

import attr

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from twisted.web.client import ResponseFailed

from otter.util.deferredutils import retry_and_timeout
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    terminal_errors_except
)


def retry(reason, timeout=60, period=3, clock=reactor):
    """
    Helper that decorates a function to retry it until success it succeeds or
    times out.  Assumes the function will raise :class:`TransientRetryError`
    if it can be retried.
    """
    def decorator(f):
        @wraps(f)
        def retrier(*args, **kwargs):
            return retry_and_timeout(
                partial(f, *args, **kwargs), timeout,
                can_retry=terminal_errors_except(TransientRetryError),
                next_interval=repeating_interval(period),
                clock=clock,
                deferred_description=reason
            )
        return retrier
    return decorator


@attr.s
class RetryingTreq(object):
    """
    Get a treq that retries on every
    :obj:`twisted.web._newclient.ResponseNeverReceived` error and every
    413 overLimit error (which we can detect only because Rackspace services
    use Repose to do rate-limiting, and Repose produces errors in the same
    format).
    """
    treq = attr.ib()
    timeout = attr.ib()
    period = attr.ib()
    clock = attr.ib(default=reactor)

    def _treq_retry(self, f):
        """
        Decorator that retries a treq request if there is a connection error
        or a 413 overlimit error.
        """
        @wraps(f)
        def retrier(url, *args, **kwargs):
            reason = "Retrying {0} {1}.".format(f.__name__.upper(), url)

            @retry(reason, self.timeout, self.period, clock=self.clock)
            @inlineCallbacks
            def make_request():
                try:
                    r = yield f(url, *args, **kwargs)
                except ResponseFailed:
                    raise TransientRetryError()
                else:
                    if r.code == 413:
                        body = yield self.treq.content(r)
                        if 'overLimit' in body:
                            raise TransientRetryError()

                    returnValue(r)

            return make_request()
        return retrier

    def __getattr__(self, attribute):
        """
        Wrap treq request functions with retrying, otherwise return treq
        functions.
        """
        treq_attribute = getattr(self.treq, attribute)
        # this should also handle 'request', but we don't use that in the
        # tests yet and it's slightly more special since we have to pull
        # the method out of the args
        if attribute not in ('get', 'delete', 'put', 'post', 'patch',
                             'head'):
            return treq_attribute
        return self._treq_retry(treq_attribute)
