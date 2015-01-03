"""Effect dispatchers for Otter."""

from effect import base_dispatcher, ComposedDispatcher, TypeDispatcher
from effect.twisted import make_twisted_dispatcher

from .auth import (
    Authenticate, perform_authenticate,
    InvalidateToken, perform_invalidate_token,
)
from .util.pure_http import (
    Request, perform_request,
)
from .util.retry import (
    Retry, perform_retry,
)


def get_dispatcher(reactor):
    """
    Get an Effect dispatcher that can handle all the effects in Otter,
    suitable for passing to :func:`effect.perform`.
    """
    return ComposedDispatcher([
        base_dispatcher,
        TypeDispatcher({
            Authenticate: perform_authenticate,
            InvalidateToken: perform_invalidate_token,
            Request: perform_request,
            Retry: perform_retry,
        }),
        make_twisted_dispatcher(reactor),
    ])
