from characteristic import Attribute, attributes

from pyrsistent import PSet

from otter.convergence.model import ServerState


class OvershootError(AssertionError):
    """
    Raised when Otter creates more servers than a launch configuration
    specifies.
    """
    pass


class UndershootError(AssertionError):
    """
    Raised when Otter removes more servers than a launch configuration
    specifies.
    """
    pass


@attributes([Attribute("servers", instance_of=PSet),
             Attribute("lb_connections", instance_of=PSet)],
            apply_immutable=True)
class GroupState(object):
    """
    The externally visible state of a group at a point in time.

    :attr pset servers: Set of the servers in the group.
    :attr pset lb_nodes: Set of the load balancer nodes in the group.
    """


def measure_progress(prev_state, curr_state, desired_state):
    """
    How many steps have been made towards the desired state between
    the previous and current states?

    XXX: The NovaServer instances we get from GroupState don't
    describe their own flavor/image, making it impossible to see if
    the new servers are of the correct type.

    :param GroupState prev_state: The previous state of a scaling group.
    :param GroupState curr_state: The current state of a scaling group.
    :param DesiredState desired_state: The desired state of a scaling group.
    :return: The number of steps made towards the desired.
    :rtype: int
    :raises UndershootError: If Autoscale removes more servers than a launch
     configuration specifies.
    :raises OvershootError: If Autoscale creates more servers than a launch
     configuration specifies.
    """
    prev_capacity = _count_live_servers(prev_state.servers)
    curr_capacity = _count_live_servers(curr_state.servers)
    capacity_delta = curr_capacity - prev_capacity
    desired = desired_state.desired

    if prev_capacity > desired and curr_capacity < desired:
        msg = "Undershoot: prev capacity = %d, desired = %d, current = %d"
        raise UndershootError(msg.format(
            prev_capacity, desired, curr_capacity
        ))
    elif prev_capacity < desired and curr_capacity > desired:
        msg = "Overshoot: prev capacity = %d, desired = %d, current = %d"
        raise OvershootError(msg.format(
            prev_capacity, desired, curr_capacity
        ))

    if capacity_delta < 0 and curr_capacity < desired:
        return 0
    elif capacity_delta > 0 and curr_capacity > desired:
        return 0
    else:
        return abs(capacity_delta)


def _count_live_servers(servers):
    """
    Count servers that are active or building.
    """
    live_states = [ServerState.BUILD, ServerState.ACTIVE]
    return len([s for s in servers if s.state in live_states])


def _count_dead_servers(servers):
    """
    Count servers that are in error state.
    """
    return len([s for s in servers if s.state is ServerState.ERROR])
