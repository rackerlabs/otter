"""
Intents for worker code including the controller, supervisor, and launch server
worker.
"""
from functools import partial

from characteristic import attributes

from effect import TypeDispatcher

from txeffect import deferred_performer


@attributes(['log', 'transaction_id', 'scaling_group', 'server_id'])
class EvictServerFromScalingGroup(object):
    """
    An Effect intent which indicates that a server should be evicted from a
    particular group.
    """


@deferred_performer
def perform_evict_server(supervisor, dispatcher, intent):
    """
    Perform evicting a server from the group.
    """
    return supervisor.scrub_otter_metadata(
        intent.log, intent.transaction_id,
        intent.scaling_group.tenant_id,
        intent.server_id)


def get_eviction_dispatcher(supervisor):
    """
    Get a dispatcher with :class:`EvictServerFromScalingGroup`'s performer.

    :param supervisor: a :class:`otter.supervisor.ISupervisor` provider
    """
    return TypeDispatcher({
        EvictServerFromScalingGroup: partial(perform_evict_server, supervisor)
    })
