"""Effect dispatchers for Otter."""

from effect import (
    ComposedDispatcher,
    TypeDispatcher,
    base_dispatcher)
from effect.ref import reference_dispatcher

from txeffect import make_twisted_dispatcher

from .auth import (
    Authenticate,
    InvalidateToken,
    perform_authenticate,
    perform_invalidate_token,
)
from .cloud_client import get_cloud_client_dispatcher
from .log.intents import get_log_dispatcher, get_msg_time_dispatcher
from .models.cass import get_cql_dispatcher
from .models.intents import get_model_dispatcher
from .util.pure_http import Request, perform_request
from .util.retry import Retry, perform_retry
from .util.zk import get_zk_dispatcher
from .worker_intents import get_eviction_dispatcher


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
        reference_dispatcher,
    ])


def get_full_dispatcher(reactor, authenticator, log, service_configs,
                        kz_client, store, supervisor, cass_client):
    """
    Return a dispatcher that can perform all of Otter's effects.
    """
    return ComposedDispatcher([
        get_legacy_dispatcher(reactor, authenticator, log, service_configs),
        get_zk_dispatcher(kz_client),
        get_model_dispatcher(log, store),
        get_eviction_dispatcher(supervisor),
        get_msg_time_dispatcher(reactor),
        get_cql_dispatcher(cass_client)
    ])


def get_working_cql_dispatcher(reactor, cass_client):
    """
    Get dispatcher with CQLQueryExecute performer along with any other
    dependent performers to make it work
    """
    return ComposedDispatcher([
        get_simple_dispatcher(reactor),
        get_cql_dispatcher(cass_client)
    ])


def get_legacy_dispatcher(reactor, authenticator, log, service_configs):
    """
    Return a dispatcher that can perform effects that are needed by the old
    worker code.
    """
    return ComposedDispatcher([
        get_cloud_client_dispatcher(
            reactor, authenticator, log, service_configs),
        get_simple_dispatcher(reactor),
        get_log_dispatcher(log, {})
    ])
