"""Effect dispatchers for Otter."""

from functools import partial

from cql.connection import connect

from effect import (
    ComposedDispatcher,
    ParallelEffects,
    TypeDispatcher,
    base_dispatcher,
    sync_perform,
    sync_performer)
from effect.twisted import make_twisted_dispatcher

from .auth import (
    Authenticate,
    InvalidateToken,
    perform_authenticate,
    perform_invalidate_token,
)
from .http import TenantScope, perform_tenant_scope
from .models.cass import CQLQueryExecute, perform_cql_query
from .util.pure_http import Request, perform_request
from .util.retry import Retry, perform_retry


def get_simple_dispatcher(reactor):
    """
    Get an Effect dispatcher that can handle most of the effects in Otter,
    suitable for passing to :func:`effect.perform`. Note that this does NOT
    handle :obj:`ServiceRequest` and :obj:`TenantScope`.

    Usually, :func:`get_full_dispatcher` should be used instead of this
    function. The simple dispatcher should only be used in tests or legacy
    code.
    """
    return ComposedDispatcher([
        base_dispatcher,
        TypeDispatcher({
            Authenticate: perform_authenticate,
            InvalidateToken: perform_invalidate_token,
            Request: perform_request,
            Retry: perform_retry
        }),
        make_twisted_dispatcher(reactor),
    ])


def get_full_dispatcher(reactor, authenticator, log, service_config):
    """
    Return a dispatcher that can perform all of Otter's effects.
    """
    return ComposedDispatcher([
        TypeDispatcher({
            TenantScope: partial(perform_tenant_scope, authenticator, log,
                                 service_config)}),
        get_simple_dispatcher(reactor),
    ])


def get_cql_dispatcher(reactor, connection):
    """
    Get dispatcher with `CQLQueryExecute`'s performer in it

    :param reactor: Twisted reactor
    :param connection: Silverberg connection
    """
    return ComposedDispatcher([
        get_simple_dispatcher(reactor),
        TypeDispatcher({
            CQLQueryExecute: partial(perform_cql_query, connection)
        })
    ])
