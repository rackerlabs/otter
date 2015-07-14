"""
Module for retrying integration test utilities.
"""

from functools import partial, wraps

from twisted.internet import reactor

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
