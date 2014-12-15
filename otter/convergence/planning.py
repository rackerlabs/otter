"""Code related to creating a plan for convergence."""

from pyrsistent import pbag, s, pset

from toolz.curried import filter, groupby
from toolz.itertoolz import concat, concatv, mapcat

from otter.convergence.model import NodeCondition, ServerState
from otter.convergence.steps import (
    AddNodesToLoadBalancer,
    ChangeLoadBalancerNode,
    CreateServer,
    DeleteServer,
    RemoveFromLoadBalancer,
    SetMetadataItemOnServer,
)
from otter.util.fp import partition_bool, partition_groups


def _remove_from_lb_with_draining(timeout, nodes, now):
    """
    Produce a series of steps that will eventually remove all the given nodes.
    It does this in three steps:

    For any particular node in ``nodes``:

    1. If the timeout is greater than zero, and the node is ``ENABLED``, the
       node will be changed to ``DRAINING``.

    2. If the node is ``DRAINING``, and the timeout (greater than zero) has
       already expired or there are no more active connections, the node will
       be removed from the load balancer.  If the timeout (greater than zero)
       has not expired and active connections != 0, then nothing is done to the
       node.

    3. If the node is in any other state other than `DRAINING` or `ENABLED`, or
       if the timeout is zero, it will be removed from the load balancer.

    :param float timeout: the time the node should remain in draining until
        removed
    :param list nodes: `list` of :obj:`LBNode` that should be
        drained, then removed
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.

    :rtype: `list` of :class:`IStep`
    """
    to_drain = []
    in_drain = []

    # only put nodes into draining if a timeout is specified
    if timeout > 0:
        draining, to_drain = partition_groups(
            lambda n: n.config.condition, nodes, [NodeCondition.DRAINING,
                                                  NodeCondition.ENABLED])

        # Nothing should be done to these, because the timeout has not expired
        # and there are still active connections
        in_drain = [node for node in draining
                    if (now - node.drained_at < timeout and
                        (node.connections is None or node.connections > 0))]

    removes = [RemoveFromLoadBalancer(lb_id=node.lb_id, node_id=node.node_id)
               for node in (set(nodes) - set(to_drain) - set(in_drain))]

    changes = [ChangeLoadBalancerNode(lb_id=node.lb_id,
                                      node_id=node.node_id,
                                      condition=NodeCondition.DRAINING,
                                      weight=node.config.weight,
                                      type=node.config.type)
               for node in to_drain]

    return removes + changes


def _converge_lb_state(desired_lb_state, current_lb_nodes, ip_address):
    """
    Produce a series of steps to converge a server's current load balancer
    state towards its desired load balancer state.

    The server will be removed from any extra load balancers the server
    is currently on, and it will be added on the correct port, with the correct
    weight, and correct status, to the desired load balancers.

    :param dict desired_lb_state: As per :obj:`DesiredGroupState`.desired_lbs
    :param list current_lb_nodes: `list` of :obj:`LBNode`
    :param str ip_address: the IP address of the server to converge

    Note: this supports user customizable types (e.g. PRIMARY or SECONDARY), but
    in practice it should probably only be added as PRIMARY.  SECONDARY can only
    be used if load balancer health monitoring is enabled, and would be used as
    backup servers anyway.

    :rtype: `list` of :class:`IStep`
    """
    desired = {
        (lb_id, config.port): config
        for lb_id, configs in desired_lb_state.items()
        for config in configs}
    current = {
        (node.lb_id, node.config.port): node
        for node in current_lb_nodes}
    desired_idports = set(desired)
    current_idports = set(current)

    adds = [
        AddNodesToLoadBalancer(
            lb_id=lb_id,
            address_configs=s((ip_address, desired[lb_id, port])))
        for lb_id, port in desired_idports - current_idports]

    # TODO: Removes could be replaced with _remove_from_lb_with_draining if
    # we wanted to support draining for moving load balancers too
    removes = [
        RemoveFromLoadBalancer(
            lb_id=lb_id,
            node_id=current[lb_id, port].node_id)
        for lb_id, port in current_idports - desired_idports]
    changes = [
        ChangeLoadBalancerNode(
            lb_id=lb_id,
            node_id=current[lb_id, port].node_id,
            condition=desired_config.condition,
            weight=desired_config.weight,
            type=desired_config.type)
        for (lb_id, port), desired_config in desired.iteritems()
        if ((lb_id, port) in current
            and current[lb_id, port].config != desired_config)]
    return adds + removes + changes


def _drain_and_delete(server, timeout, current_lb_nodes, now):
    """
    If server is not already in draining state, put it into draining state.
    If the server is free of load balancers, just delete it.
    """
    lb_draining_steps = _remove_from_lb_with_draining(timeout, current_lb_nodes,
                                                      now)

    # if there are no load balancers that are waiting on draining timeouts or
    # connections, just delete the server too
    if (len(lb_draining_steps) == len(current_lb_nodes) and
        all([isinstance(step, RemoveFromLoadBalancer)
             for step in lb_draining_steps])):
        return lb_draining_steps + [DeleteServer(server_id=server.id)]

    # if the server is not already in draining state, put it into draining
    if server.state != ServerState.DRAINING:
        return lb_draining_steps + [
            SetMetadataItemOnServer(server_id=server.id,
                                    key='rax:auto_scaling_draining',
                                    value='draining')]

    return lb_draining_steps


def converge(desired_state, servers_with_cheese, load_balancer_contents, now,
             timeout=3600):
    """
    Create steps that indicate how to transition from the state provided
    by the given parameters to the :obj:`DesiredGroupState` described by
    ``desired_state``.

    :param DesiredGroupState desired_state: The desired group state.
    :param set servers_with_cheese: a list of :obj:`NovaServer` instances.
        This must only contain servers that are being managed for the specified
        group.
    :param load_balancer_contents: a set of :obj:`LBNode` instances.  This must
        contain all the load balancer mappings for all the load balancers on the
        tenant.
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.
    :param float timeout: Number of seconds after which we will delete a server
        in BUILD.

    :rtype: :obj:`pbag` of `IStep`
    """
    lbs_by_address = groupby(lambda n: n.address, load_balancer_contents)

    newest_to_oldest = sorted(servers_with_cheese, key=lambda s: -s.created)

    servers_in_error, servers_in_active, servers_in_build, draining_servers = (
        partition_groups(
            lambda s: s.state, newest_to_oldest, [ServerState.ERROR,
                                                  ServerState.ACTIVE,
                                                  ServerState.BUILD,
                                                  ServerState.DRAINING]))

    building_too_long, waiting_for_build = partition_bool(
        lambda server: now - server.created >= timeout,
        servers_in_build)

    create_server = CreateServer(launch_config=desired_state.launch_config)

    # delete any servers that have been building for too long
    delete_timeout_steps = [DeleteServer(server_id=server.id)
                            for server in building_too_long]

    # create servers
    create_steps = [create_server] * (desired_state.desired
                                      - (len(servers_in_active)
                                         + len(waiting_for_build)))

    # Scale down over capacity, starting with building, then active,
    # preferring older.  Also, finish draining/deleting servers already in
    # draining state
    servers_to_delete = (servers_in_active + waiting_for_build)[desired_state.desired:]

    def drain_and_delete_a_server(server):
        return _drain_and_delete(
            server, desired_state.draining_timeout,
            lbs_by_address.get(server.servicenet_address, []), now)

    scale_down_steps = list(mapcat(drain_and_delete_a_server,
                                   servers_to_delete + draining_servers))

    # delete all servers in error - draining does not need to be handled because
    # servers in error presumably are not serving traffic anyway
    delete_error_steps = (
        [DeleteServer(server_id=server.id) for server in servers_in_error] +
        [RemoveFromLoadBalancer(lb_id=lb_node.lb_id,
                                node_id=lb_node.node_id)
         for server in servers_in_error
         for lb_node in lbs_by_address.get(server.servicenet_address, [])])

    # converge all the servers that remain to their desired load balancer state
    still_active_servers = filter(lambda s: s not in servers_to_delete,
                                  servers_in_active)
    lb_converge_steps = [
        step
        for server in still_active_servers
        for step in _converge_lb_state(
            desired_state.desired_lbs,
            lbs_by_address.get(server.servicenet_address, []),
            server.servicenet_address)
        if server.servicenet_address]

    return pbag(create_steps
                + scale_down_steps
                + delete_error_steps
                + delete_timeout_steps
                + lb_converge_steps)


_optimizers = {}


def _optimizer(step_type):
    """
    A decorator for a type-specific optimizer.

    Usage::

        @_optimizer(StepTypeToOptimize)
        def optimizing_function(steps_of_that_type):
           return iterable_of_optimized_steps
    """
    def _add_to_optimizers(optimizer):
        _optimizers[step_type] = optimizer
        return optimizer
    return _add_to_optimizers


@_optimizer(AddNodesToLoadBalancer)
def _optimize_lb_adds(lb_add_steps):
    """
    Merge together multiple :obj:`AddNodesToLoadBalancer`, per load balancer.

    :param steps_by_lb: Iterable of :obj:`AddNodesToLoadBalancer`.
    """
    steps_by_lb = groupby(lambda s: s.lb_id, lb_add_steps)
    return [
        AddNodesToLoadBalancer(
            lb_id=lbid,
            address_configs=pset(reduce(lambda s, y: s.union(y),
                                        [step.address_configs for step in steps])))
        for lbid, steps in steps_by_lb.iteritems()
    ]


def optimize_steps(steps):
    """
    Optimize steps.

    Currently only optimizes per step type. See the :func:`_optimizer`
    decorator for more information on how to register an optimizer.

    :param pbag steps: Collection of steps.
    :return: a pbag of steps.
    """
    def grouping_fn(step):
        step_type = type(step)
        if step_type in _optimizers:
            return step_type
        else:
            return "unoptimizable"

    steps_by_type = groupby(grouping_fn, steps)
    unoptimizable = steps_by_type.pop("unoptimizable", [])
    omg_optimized = concat(_optimizers[step_type](steps)
                           for step_type, steps in steps_by_type.iteritems())
    return pbag(concatv(omg_optimized, unoptimizable))
