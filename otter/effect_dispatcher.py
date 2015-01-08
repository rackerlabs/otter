"""Effect dispatchers for Otter."""

from functools import partial

from effect import base_dispatcher, ComposedDispatcher, TypeDispatcher
from effect.twisted import make_twisted_dispatcher

from .auth import (
    Authenticate, perform_authenticate,
    InvalidateToken, perform_invalidate_token)
from .util.pure_http import Request, perform_request
from .util.retry import Retry, perform_retry

from otter.http import TenantScope, perform_tenant_scope


def get_simple_dispatcher(reactor):
    """
    Get an Effect dispatcher that can handle most of the effects in Otter,
    suitable for passing to :func:`effect.perform`. Note that this does NOT
    handle :obj:`ServiceRequest` and :obj:`TenantScope`.
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


def get_full_dispatcher(reactor, authenticator, log, service_mapping, region):
    """
    Return a dispatcher that can perform all of Otter's effects.
    """
    return ComposedDispatcher([
        TypeDispatcher({
            TenantScope: partial(perform_tenant_scope, authenticator, log,
                                 service_mapping, region)}),
        get_simple_dispatcher(reactor),
    ])
