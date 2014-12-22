"""
:module:`otter.worker.launch_server_v1`-specific code for RackConnect v3.

At some point, this should just be moved into that module.
"""
from effect.twisted import perform
from functools import partial
from operator import itemgetter
from otter.effect_dispatcher import get_dispatcher
from otter.convergence.steps import BulkAddToRCv3, BulkRemoveFromRCv3
from otter.convergence.effecting import _reqs_to_effect
from twisted.internet import reactor


def _generic_rcv3_request(step_class, request_func, lb_id, server_id,
                          _reactor=reactor):
    """
    Perform a generic RCv3 bulk step on a single (lb, server) pair.

    :param IStep step_class: The step class to perform the action.
    :param callable request_func: A request function.
    :param str lb_id: The id of the RCv3 load balancer to act on.
    :param str server_id: The Nova server id to act on.
    :param _reactor: The reactor used to perform the effects.
    :return: A deferred that will fire when the request has been performed,
        firing with the parsed result of the request, or :data:`None` if the
        request has no body.
    """
    step = step_class(lb_node_pairs=[(lb_id, server_id)])
    effect = _reqs_to_effect(request_func, [step.as_request()])
    # The result will be a list (added by ParallelEffects) of
    # results. In this code, we're only performing one request, so we
    # know there will only be one element in that list. Our contract
    # is that we return the result of the request, so we discard the
    # outer list.
    dispatcher = get_dispatcher(_reactor)
    return perform(dispatcher, effect).addCallback(itemgetter(0))


add_to_rcv3 = partial(_generic_rcv3_request, BulkAddToRCv3)
remove_from_rcv3 = partial(_generic_rcv3_request, BulkRemoveFromRCv3)
