"""
:module:`otter.worker.launch_server_v1`-specific code for RackConnect v3.

At some point, this should just be moved into that module.
"""
from functools import partial
from operator import itemgetter

from effect import Effect

from pyrsistent import s

from txeffect import perform

from otter.cloud_client import TenantScope
from otter.convergence.steps import BulkAddToRCv3, BulkRemoveFromRCv3
from otter.util.pure_http import has_code


def _generic_rcv3_request(step_class, request_bag, lb_id, server_id):
    """
    Perform a generic RCv3 bulk step on a single (lb, server) pair.

    :param IStep step_class: The step class to perform the action.
    :param request_bag: An object with a bunch of useful data on it.
    :param str lb_id: The id of the RCv3 load balancer to act on.
    :param str server_id: The Nova server id to act on.
    :return: A deferred that will fire when the request has been performed,
        firing with the parsed result of the request, or :data:`None` if the
        request has no body.
    """
    effect = step_class(lb_node_pairs=s((lb_id, server_id)))._bare_effect()

    if step_class is BulkAddToRCv3:
        svc_req = effect.intent
        codes = set(svc_req.success_pred.codes) - set([409])
        svc_req.success_pred = has_code(*codes)

    # Unfortunate that we have to TenantScope here, but here's where we're
    # performing.
    scoped = Effect(TenantScope(effect, request_bag.tenant_id))
    d = perform(request_bag.dispatcher, scoped)
    return d.addCallback(itemgetter(1))


add_to_rcv3 = partial(_generic_rcv3_request, BulkAddToRCv3)
remove_from_rcv3 = partial(_generic_rcv3_request, BulkRemoveFromRCv3)
