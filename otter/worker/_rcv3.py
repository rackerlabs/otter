"""
:module:`otter.worker.launch_server_v1`-specific code for RackConnect v3.

At some point, this should just be moved into that module.
"""
from effect import Effect

from pyrsistent import pset

from toolz.functoolz import curry

from txeffect import perform

from otter.cloud_client import TenantScope, rcv3 as cc_rcv3


@curry
def _generic_rcv3_request(operation, request_bag, lb_id, server_id):
    """
    Perform a generic RCv3 bulk operation on a single (lb, server) pair.

    :param callable operation: RCv3 function to perform on (lb, server) pair.
    :param request_bag: An object with a bunch of useful data on it.
    :param str lb_id: The id of the RCv3 load balancer to act on.
    :param str server_id: The Nova server id to act on.
    :return: A deferred that will fire when the request has been performed,
        firing with the parsed result of the request, or :data:`None` if the
        request has no body.
    """
    eff = operation(pset([(lb_id, server_id)]))
    scoped = Effect(TenantScope(eff, request_bag.tenant_id))
    return perform(request_bag.dispatcher, scoped)


def add_to_rcv3(request_bag, lb_id, server_id):
    return _generic_rcv3_request(cc_rcv3.bulk_add, request_bag,
                                 lb_id, server_id)


def remove_from_rcv3(request_bag, lb_id, server_id):
    return _generic_rcv3_request(cc_rcv3.bulk_delete, request_bag,
                                 lb_id, server_id)
