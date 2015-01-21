"""
:module:`otter.worker.launch_server_v1`-specific code for RackConnect v3.

At some point, this should just be moved into that module.
"""
from functools import partial
from operator import itemgetter

from effect.twisted import perform

from twisted.internet import reactor

from otter.convergence.effecting import steps_to_effect
from otter.convergence.steps import BulkAddToRCv3, BulkRemoveFromRCv3
from otter.effect_dispatcher import get_simple_dispatcher


def _generic_rcv3_request(step_class, request_bag, lb_id, server_id):
    """
    Perform a generic RCv3 bulk step on a single (lb, server) pair.

    :param IStep step_class: The step class to perform the action.
    :param request_bag: An object with a bunch of useful data on it. Called
        a ``request_func`` by other worker/supervisor code.
    :param str lb_id: The id of the RCv3 load balancer to act on.
    :param str server_id: The Nova server id to act on.
    :return: A deferred that will fire when the request has been performed,
        firing with the parsed result of the request, or :data:`None` if the
        request has no body.
    """
    step = step_class(lb_node_pairs=[(lb_id, server_id)])
    effect = steps_to_effect([step])
    # The result will be a list (added by ParallelEffects) of
    # results. In this code, we're only performing one request, so we
    # know there will only be one element in that list. Our contract
    # is that we return the result of the request, so we discard the
    # outer list.
    # TODO: TenantScope!
    return perform(request_bag.dispatcher, effect).addCallback(itemgetter(0))


add_to_rcv3 = partial(_generic_rcv3_request, BulkAddToRCv3)
remove_from_rcv3 = partial(_generic_rcv3_request, BulkRemoveFromRCv3)
