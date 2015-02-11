"""Effect dispatchers for Otter."""

from functools import partial

from cql.connection import connect

from effect import ComposedDispatcher, TypeDispatcher, base_dispatcher, sync_performer
from effect.twisted import make_twisted_dispatcher

from .auth import (
    Authenticate,
    InvalidateToken,
    perform_authenticate,
    perform_invalidate_token,
)
from .http import TenantScope, perform_tenant_scope
from .models.cass import CQLQueryExecute, perform_query_sync
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
            Retry: perform_retry,
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


def get_sync_cql_dispatcher(cursor):
    """
    Get dispatcher with `CQLQueryExecute`'s synchronous performer in it

    :param cql: CQL cursor
    """
    return ComposedDispatcher([
        base_dispatcher,
        TypeDispatcher({
            CQLQueryExecute: partial(perform_query_sync, cursor),
            ParallelEffects: perform_serial
        })
    ])


@sync_performer
def perform_serial(disp, intent):
    """
    Performs parallel effects serially. Useful when testing or simple cases
    """
    return map(partial(perform, disp), intent.effects)
