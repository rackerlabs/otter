"""Effect dispatchers for Otter."""

from functools import partial

from effect import base_dispatcher, ComposedDispatcher, TypeDispatcher
from effect.twisted import legacy_dispatcher, make_twisted_dispatcher

from otter.http import TenantScope, perform_tenant_scope


def get_simple_dispatcher(reactor):
    """
    Get an Effect dispatcher that can handle most of the effects in Otter,
    suitable for passing to :func:`effect.perform`. Note that this does NOT
    handle :obj:`ServiceRequest` and :obj:`TenantScope`.
    """
    # TODO: Get rid of the "legacy_dispatcher" here, after we get rid of all use
    # of "perform_effect" methods on intents.
    return ComposedDispatcher([
        base_dispatcher,
        legacy_dispatcher,
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
