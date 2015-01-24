from characteristic import Attribute, attributes

from pyrsistent import pset

from otter.convergence.model import NovaServer

@attributes([
    Attribute("servers"),
    Attribute("lb_connections")
])
class GroupState(object):
    """
    The externally visible state of a group at a point in time.

    :attr pset servers: Set of the servers in the group.
    :attr pset lb_nodes: Set of the load balancer nodes in the group.
    """

def measure_progress(previous_state, current_state, desired_state):
    """
    How many steps have been made towards the desired state between
    the previous and current states?

    XXX: The NovaServer instances we get from GroupState don't
    describe their own flavor/image, making it impossible to see if
    the new servers are of the correct type.

    :param GroupState previous_state: The previous state of a scaling group.
    :param GroupState current_state: The current state of a scaling group.
    :param DesiredState desired_state: The desired state of a scaling group.
    :return: The number of steps made towards the desired.
    :rtype: int
    :raises AssertionError: If progress regressed.
    """
    prev_capacity = len(previous_state.servers)
    curr_capacity = len(current_state.servers)
    capacity_delta = curr_capacity - prev_capacity
    desired = desired_state.desired

    if prev_capacity > desired and curr_capacity < desired:
        raise AssertionError("Undershot the desired capacity")
    elif prev_capacity < desired and curr_capacity > desired:
        raise AssertionError("Overshot the desired capacity")

    return abs(capacity_delta)

def _sign(n):
    """
    Returns the sign of n.
    """
    return cmp(n, 0)
