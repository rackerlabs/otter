"""Code related to creating a plan for convergence."""

from functools import partial

from pyrsistent import pbag, pmap, pset

from toolz.curried import filter, groupby
from toolz.itertoolz import concat, concatv, mapcat

from otter.convergence.model import (
    CLBDescription, CLBNode, CLBNodeCondition, IDrainable, ServerState)
from otter.convergence.steps import (
    AddNodesToCLB,
    ChangeCLBNode,
    CreateServer,
    DeleteServer,
    RemoveNodesFromCLB,
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
    desired_lbs = set(concat(server.desired_lbs.values()))
    desired_matching_existing = [
        (desired, node) for desired in desired_lbs
        for node in current_lb_nodes
        if desired.equivalent_definition(node.description)]

    if desired_matching_existing:
        met_desireds, good_nodes = zip(*desired_matching_existing)
    else:
        met_desireds = good_nodes = ()

    adds = [
        add_server_to_lb(server=server, description=desired)
        for desired in desired_lbs - set(met_desireds)
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
    """
    lb_draining_steps = _remove_from_lb_with_draining(
        timeout, current_lb_nodes, now)

    # if there are no load balancers that are waiting on draining timeouts or
    # connections, just delete the server too
    if (len(lb_draining_steps) == len(current_lb_nodes) and
        all([isinstance(step, RemoveNodesFromCLB)
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
    :param load_balancer_contents: a set of :obj:`ILBNode` providers.  This
        must contain all the load balancer mappings for all the load balancers
        (of all types) on the tenant.
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
            server, desired_state.draining_timeout,
            lbs_by_address.get(server.servicenet_address, []), now)

    scale_down_steps = list(mapcat(drain_and_delete_a_server,
                                   servers_to_delete + draining_servers))

    # delete all servers in error - draining does not need to be
    # handled because servers in error presumably are not serving
    # traffic anyway
    delete_error_steps = (
        [DeleteServer(server_id=server.id) for server in servers_in_error] +
        [RemoveNodesFromCLB(lb_id=lb_node.description.lb_id,
                            node_ids=(lb_node.node_id,))
         for server in servers_in_error
         for lb_node in lbs_by_address.get(server.servicenet_address, [])])

    # converge all the servers that remain to their desired load balancer state
    still_active_servers = filter(lambda s: s not in servers_to_delete,
                                  servers_in_active)
    lb_converge_steps = [
        step
        for server in still_active_servers
        for step in _converge_lb_state(
            server,
            lbs_by_address.get(server.servicenet_address, []))
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


def _register_bulk_clb_optimizer(step_class, attr_name):
    """
    Merge together multiple CLB bulk steps per load balancer.  This function
    is for generating and registering the :obj:`AddNodesToCLB` and
    :obj:`RemoveNodesFromCLB` optimizers.

    :param step_class: One of :obj:`AddNodesToCLB` or :obj:`RemoveNodesFromCLB`
    :param attr_name: The attribute name on the class that is the iterable that
        needs to be concatenated together to make an optimized step.

    :return: Nothing, because this just registers the optimizers with the
        module.
    """
    def optimize_steps(clb_steps):
        steps_by_lb = groupby(lambda s: s.lb_id, clb_steps)
        return [
            step_class(**{
                'lb_id': lb_id,
                attr_name: pset(concat(getattr(s, attr_name) for s in steps))})
            for lb_id, steps in steps_by_lb.iteritems()
        ]

    _optimizer(step_class)(optimize_steps)

_register_bulk_clb_optimizer(AddNodesToCLB, 'address_configs')
_register_bulk_clb_optimizer(RemoveNodesFromCLB, 'node_ids')


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


_DEFAULT_STEP_LIMITS = pmap({
    CreateServer: 3
})


def _limit_step_count(steps, step_limits):
    """
    Limits step count by type.

    :param steps: An iterable of steps.
    :param step_limits: A dict mapping step classes to their maximum allowable
        count. Classes not present in this dict have no limit.
    :return: The input steps
    :rtype: pset
    """
    return pbag(concat(typed_steps[:step_limits.get(cls)]
                       for (cls, typed_steps)
                       in groupby(type, steps).iteritems()))


_default_limit_step_count = partial(
    _limit_step_count, step_limits=_DEFAULT_STEP_LIMITS)


def plan(desired_group_state, servers, lb_nodes, now):
    """
    Get an optimized convergence plan.

    Takes the same arguments as :func:`converge`.
    """
    steps = converge(desired_group_state, servers, lb_nodes, now)
    steps = _default_limit_step_count(steps)
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


def remove_node_from_lb(node):
    """
    Remove a node from the load balancing entity.

    :ivar node: The node to be removed.
    :type node: :class:`ILBNode` provider
    """
    if isinstance(node, CLBNode):
        return RemoveNodesFromCLB(lb_id=node.description.lb_id,
                                  node_ids=(node.node_id,))


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
