"""
:module:`otter.worker.launch_server_v1`-specific code for RackConnect v3.

At some point, this should just be moved into that module.
"""
from effect.twisted import perform
from functools import partial
from operator import itemgetter
from otter.convergence import BulkAddToRCv3, BulkRemoveFromRCv3, _reqs_to_effect
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
    :return: A deferred that will fire when the
    """
    step = step_class(lb_node_pairs=[(lb_id, server_id)])
    effect = _reqs_to_effect(request_func, [step.as_request()])
    return perform(_reactor, effect).addCallback(itemgetter(0))


add_to_rcv3 = partial(_generic_rcv3_request, BulkAddToRCv3)
remove_from_rcv3 = partial(_generic_rcv3_request, BulkRemoveFromRCv3)
