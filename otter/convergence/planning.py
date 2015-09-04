"""Code related to creating a plan for convergence."""

from pyrsistent import pbag, pset

from toolz.curried import filter
from toolz.itertoolz import mapcat

from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    DRAINING_METADATA,
    ErrorReason,
    IDrainable,
    RCv3Description,
    RCv3Node,
    ServerState)
from otter.convergence.steps import (
    AddNodesToCLB,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    ConvergeLater,
    CreateServer,
    DeleteServer,
    RemoveNodesFromCLB,
    SetMetadataItemOnServer,
)
from otter.convergence.transforming import limit_steps_by_count, optimize_steps
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
    :param list nodes: `list` of :obj:`CLBNode` that should be
        drained, then removed
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.

    :rtype: `list` of :class:`IStep`
    """
    to_drain = ()
    in_drain = ()

    # only put nodes into draining if a timeout is specified
    if timeout > 0:
        draining, to_drain = partition_bool(
            lambda node: node.currently_draining(),
            [node for node in nodes
             if IDrainable.providedBy(node) and node.is_active()])

        # Nothing should be done to these, because the timeout has not expired
        # and the nodes are still active
        in_drain = [node for node in draining
                    if not node.is_done_draining(now, timeout)]

    removes = [remove_node_from_lb(node=node)
               for node in (set(nodes) - set(to_drain) - set(in_drain))]

    changes = [drain_lb_node(node=node) for node in to_drain]

    return removes + changes


def _converge_lb_state(server, current_lb_nodes):
    """
    Produce a series of steps to converge a server's current load balancer
    state towards its desired load balancer state.

    The server will be removed from any extra load balancers the server
    is currently on, and it will be added on the correct port, with the correct
    weight, and correct status, to the desired load balancers.

    Note: this supports user customizable types (e.g. PRIMARY or SECONDARY),
    but in practice it should probably only be added as PRIMARY.  SECONDARY can
    only be used if load balancer health monitoring is enabled, and would be
    used as backup servers anyway.

    :param server: The server to be converged.
    :type server: :class:`NovaServer`

    :param list current_lb_nodes: `list` of :obj:`CLBNode`

    :rtype: `list` of :class:`IStep`
    """
    # list of desired configurations that match up with existing nodes
    desired_matching_existing = [
        (desired, node) for desired in server.desired_lbs
        for node in current_lb_nodes
        if desired.equivalent_definition(node.description)]

    if desired_matching_existing:
        met_desireds, good_nodes = zip(*desired_matching_existing)
    else:
        met_desireds = good_nodes = ()

    adds = [
        add_server_to_lb(server=server, description=desired)
        for desired in server.desired_lbs - set(met_desireds)
    ]

    # Removes could be replaced with _remove_from_lb_with_draining if
    # we wanted to support draining for moving load balancers too
    removes = [
        remove_node_from_lb(node=node)
        for node in set(current_lb_nodes) - set(good_nodes)
    ]

    changes = [
        change_lb_node(node=node, description=desired)
        for desired, node in desired_matching_existing
        if node.description != desired
    ]

    return [step for step in (adds + removes + changes) if step is not None]


def _drain_and_delete(server, timeout, current_lb_nodes, now):
    """
    If server is not already in draining state, put it into draining state.
    If the server is free of load balancers, just delete it.

    If a server is in building, it can just be deleted, along with any
    load balancer nodes associated with it, regardless of timeouts.
    """
    lb_draining_steps = _remove_from_lb_with_draining(
        timeout if server.state != ServerState.BUILD else 0,
        current_lb_nodes,
        now)

    # if there are no load balancers that are waiting on draining timeouts or
    # connections, just delete the server too
    if (len(lb_draining_steps) == len(current_lb_nodes) and
        all([isinstance(step, RemoveNodesFromCLB) or
             isinstance(step, BulkRemoveFromRCv3)
             for step in lb_draining_steps])):
        return lb_draining_steps + [DeleteServer(server_id=server.id)]

    # if the server is not already in draining state, put it into draining
    if server.state != ServerState.DRAINING:
        return lb_draining_steps + [
            SetMetadataItemOnServer(server_id=server.id,
                                    key=DRAINING_METADATA[0],
                                    value=DRAINING_METADATA[1])]

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
    :param load_balancer_contents: a set of :obj:`ILBNode` providers.  This
        must contain all the load balancer mappings for all the load balancers
        (of all types) on the tenant.
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.
    :param float timeout: Number of seconds after which we will delete a server
        in BUILD.
    :rtype: :obj:`pbag` of `IStep`

    """
    newest_to_oldest = sorted(servers_with_cheese, key=lambda s: -s.created)

    (servers_in_error,
     servers_in_active,
     servers_in_build,
     draining_servers,
     deleted_servers) = partition_groups(
        lambda s: s.state, newest_to_oldest, [ServerState.ERROR,
                                              ServerState.ACTIVE,
                                              ServerState.BUILD,
                                              ServerState.DRAINING,
                                              ServerState.DELETED])

    building_too_long, waiting_for_build = partition_bool(
        lambda server: now - server.created >= timeout,
        servers_in_build)

    create_server = CreateServer(server_config=desired_state.server_config)

    # delete any servers that have been building for too long
    delete_timeout_steps = [DeleteServer(server_id=server.id)
                            for server in building_too_long]

    # create servers
    create_steps = [create_server] * (desired_state.capacity
                                      - (len(servers_in_active)
                                         + len(waiting_for_build)))

    # Scale down over capacity, starting with building, then active,
    # preferring older.  Also, finish draining/deleting servers already in
    # draining state
    servers_in_preferred_order = servers_in_active + waiting_for_build
    servers_to_delete = servers_in_preferred_order[desired_state.capacity:]

    def drain_and_delete_a_server(server):
        return _drain_and_delete(
            server,
            desired_state.draining_timeout,
            [node for node in load_balancer_contents if node.matches(server)],
            now)

    scale_down_steps = list(mapcat(drain_and_delete_a_server,
                                   servers_to_delete + draining_servers))

    # delete all servers in error - draining does not need to be
    # handled because servers in error presumably are not serving
    # traffic anyway
    delete_error_steps = [
        DeleteServer(server_id=server.id) for server in servers_in_error]

    # clean up all the load balancers from deleted and errored servers
    cleanup_errored_and_deleted_steps = [
        remove_node_from_lb(lb_node)
        for server in servers_in_error + deleted_servers
        for lb_node in load_balancer_contents if lb_node.matches(server)]

    # converge all the servers that remain to their desired load balancer state
    still_active_servers = filter(lambda s: s not in servers_to_delete,
                                  servers_in_active)
    lb_converge_steps = [
        step
        for server in still_active_servers
        for step in _converge_lb_state(
            server,
            [node for node in load_balancer_contents if node.matches(server)])
        ]

    # if there are any building servers left, also return a ConvergeLater step.
    converge_later = []
    if any((s not in servers_to_delete for s in waiting_for_build)):
        converge_later = [
            ConvergeLater(reasons=[ErrorReason.String('building servers')])]

    return pbag(create_steps +
                scale_down_steps +
                delete_error_steps +
                cleanup_errored_and_deleted_steps +
                delete_timeout_steps +
                lb_converge_steps +
                converge_later)


def plan(desired_group_state, servers, lb_nodes, now, build_timeout):
    """
    Get an optimized convergence plan.

    Takes the same arguments as :func:`converge`.
    """
    steps = converge(desired_group_state, servers, lb_nodes, now,
                     timeout=build_timeout)
    steps = limit_steps_by_count(steps)
    return optimize_steps(steps)


def add_server_to_lb(server, description):
    """
    Add a server to a load balancing entity as described by `description`.

    :ivar server: The server to be added
    :type server: :class:`NovaServer`

    :ivar description: The description of the load balancer and how to add
        the server to it.
    :type description: :class:`ILBDescription` provider
    """
    if isinstance(description, CLBDescription):
        if server.servicenet_address:
            return AddNodesToCLB(
                lb_id=description.lb_id,
                address_configs=pset(
                    [(server.servicenet_address, description)]))
    elif isinstance(description, RCv3Description):
        return BulkAddToRCv3(lb_node_pairs=pset(
            [(description.lb_id, server.id)]))


def remove_node_from_lb(node):
    """
    Remove a node from the load balancing entity.

    :ivar node: The node to be removed.
    :type node: :class:`ILBNode` provider
    """
    if isinstance(node, CLBNode):
        return RemoveNodesFromCLB(lb_id=node.description.lb_id,
                                  node_ids=pset([node.node_id]))
    elif isinstance(node, RCv3Node):
        return BulkRemoveFromRCv3(lb_node_pairs=pset(
            [(node.description.lb_id, node.cloud_server_id)]))


def change_lb_node(node, description):
    """
    Change the configuration of a load balancer node.

    :ivar node: The node to be changed.
    :type node: :class:`ILBNode` provider

    :ivar description: The description of the load balancer and how to add
        the server to it.
    :type description: :class:`ILBDescription` provider
    """
    if type(node.description) == type(description):
        if isinstance(description, CLBDescription):
            return ChangeCLBNode(lb_id=description.lb_id,
                                 node_id=node.node_id,
                                 condition=description.condition,
                                 weight=description.weight,
                                 type=description.type)


def drain_lb_node(node):
    """
    Drain the node balancing node.

    :ivar node: The node to be changed.
    :type node: :class:`ILBNode` provider
    """
    if isinstance(node, CLBNode):
        return ChangeCLBNode(lb_id=node.description.lb_id,
                             node_id=node.node_id,
                             condition=CLBNodeCondition.DRAINING,
                             weight=node.description.weight,
                             type=node.description.type)
