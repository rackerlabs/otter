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
    previous_capacity = len(previous_state.servers)
    current_capacity = len(current_state.servers)
    capacity_delta = current_capacity - previous_capacity
    if capacity_delta < 0:
        raise AssertionError("boo! capacity went down")

    return capacity_delta
