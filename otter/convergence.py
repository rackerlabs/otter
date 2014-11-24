"""
Convergence.
"""

from urllib import urlencode
import calendar
import json
from itertools import izip as zip

from characteristic import attributes, Attribute
from effect import parallel
from pyrsistent import pbag, freeze, s, pset
from zope.interface import Interface, implementer

from twisted.python.constants import Names, NamedConstant

import effect

from toolz.curried import filter, groupby
from toolz.functoolz import compose, identity
from toolz.itertoolz import concat, concatv, mapcat

from otter.constants import ServiceType
from otter.util.http import append_segments
from otter.util.fp import partition_bool, partition_groups
from otter.util.retry import retry_times, exponential_backoff_interval, retry_effect
from otter.util.timestamp import from_timestamp
from otter.indexer import atom


class NodeCondition(Names):
    """Constants representing the condition a load balancer node can be in"""
    ENABLED = NamedConstant()   # Node can accept new connections.
    DRAINING = NamedConstant()  # Node cannot accept any new connections.
                                # Existing connections are forcibly terminated.
    DISABLED = NamedConstant()  # Node cannot accept any new connections.
                                # Existing connections are permitted to continue.


class NodeType(Names):
    """Constants representing the type of a load balancer node"""
    PRIMARY = NamedConstant()    # Node in normal rotation
    SECONDARY = NamedConstant()  # Node only put into normal rotation if a
                                 # primary node fails.


def get_all_server_details(request_func, batch_size=100):
    """
    Return all servers of a tenant.

    :param request_func: a request function.
    :param batch_size: number of servers to fetch *per batch*.

    NOTE: This really screams to be a independent effcloud-type API
    """
    url = append_segments('servers', 'detail')

    def get_server_details(marker):
        # sort based on query name to make the tests predictable
        query = {'limit': batch_size}
        if marker is not None:
            query.update({'marker': marker})
        urlparams = sorted(query.items())
        eff = retry_effect(
            request_func(
                ServiceType.CLOUD_SERVERS,
                'GET', '{}?{}'.format(url, urlencode(urlparams))),
            retry_times(5), exponential_backoff_interval(2))
        return eff.on(continue_)

    def continue_(response):
        servers = response['servers']
        if len(servers) < batch_size:
            return servers
        else:
            more_eff = get_server_details(servers[-1]['id'])
            return more_eff.on(lambda more_servers: servers + more_servers)
    return get_server_details(None)


def get_scaling_group_servers(request_func, server_predicate=identity):
    """
    Return tenant's servers that belong to a scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed

    :param server_predicate: function of server -> bool that determines whether
        the server should be included in the result.
    """

    def has_group_id(s):
        return 'metadata' in s and 'rax:auto_scaling_group_id' in s['metadata']

    def group_id(s):
        return s['metadata']['rax:auto_scaling_group_id']

    servers_apply = compose(groupby(group_id), filter(server_predicate), filter(has_group_id))

    eff = get_all_server_details(request_func)
    return eff.on(servers_apply)


def extract_drained_at(feed):
    """
    Extract time when node was changed to DRAINING

    :param str feed: Atom feed of the node

    :returns: EPOCH in seconds
    :rtype: float
    """
    # TODO: This function temporarily only looks at last entry assuming that
    # it was draining operation. May need to look at all entries in reverse order
    # and check for draining operation. This could include paging to further entries
    entry = atom.entries(atom.parse(feed))[0]
    summary = atom.summary(entry)
    if 'Node successfully updated' in summary and 'DRAINING' in summary:
        return calendar.timegm(from_timestamp(atom.updated(entry)).utctimetuple())
    else:
        raise ValueError('Unexpected summary: {}'.format(summary))


def get_load_balancer_contents(request_func):
    """
    Get load balancer contents as list of `LBNode`

    :param request_func: A tenant-bound, CLB-bound, auth-retry based request function
    """

    def fetch_nodes(lbs):
        lb_ids = [lb['id'] for lb in json.loads(lbs)]
        return effect.parallel(
            [request_func(
                'GET',
                append_segments('loadbalancers', str(lb_id), 'nodes')).on(json.loads)
             for lb_id in lb_ids]).on(lambda all_nodes: (lb_ids, all_nodes))

    def fetch_drained_feeds((ids, all_lb_nodes)):
        nodes = [LBNode(lb_id=_id, node_id=node['id'], address=node['address'],
                        config=LBConfig(port=node['port'], weight=node['weight'],
                                        condition=NodeCondition.lookupByName(node['condition']),
                                        type=NodeType.lookupByName(node['type'])))
                 for _id, nodes in zip(ids, all_lb_nodes)
                 for node in nodes]
        draining = [n for n in nodes if n.config.condition == NodeCondition.DRAINING]
        return effect.parallel(
            [request_func(
                'GET',
                append_segments('loadbalancers', str(n.lb_id), 'nodes',
                                '{}.atom'.format(n.node_id)))
             for n in draining]).on(lambda feeds: (nodes, draining, feeds))

    def fill_drained_at((nodes, draining, feeds)):
        for node, feed in zip(draining, feeds):
            node.drained_at = extract_drained_at(feed)
        return nodes

    return request_func('GET', 'loadbalancers').on(
        fetch_nodes).on(fetch_drained_feeds).on(fill_drained_at)


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_request():
        """
        Create a :class:`Request` object that contains relevant information for
        performing the HTTP request required for this step
        """


@attributes(['launch_config', 'desired',
             Attribute('desired_lbs', default_factory=dict, instance_of=dict),
             Attribute('draining_timeout', default_value=0.0, instance_of=float)])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    :ivar dict desired_lbs: A mapping of load balancer IDs to lists of
        :class:`LBConfig` instances.
    :ivar float draining_timeout: If greater than zero, when the server is
        scaled down it will be put into draining condition.  It will remain
        in draining condition for a maximum of ``draining_timeout`` seconds
        before being removed from the load balancer and then deleted.
    """

    def __init__(self):
        self.launch_config = freeze(self.launch_config)


@attributes(['id', 'state', 'created',
             Attribute('servicenet_address', default_value='', instance_of=str)])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    :ivar str servicenet_address: The private ServiceNet IPv4 address, if
        the server is on the ServiceNet network
    """


@attributes(["port",
             Attribute("weight", default_value=1, instance_of=int),
             Attribute("condition", default_value=NodeCondition.ENABLED,
                       instance_of=NamedConstant),
             Attribute("type", default_value=NodeType.PRIMARY,
                       instance_of=NamedConstant)])
class LBConfig(object):
    """
    Information representing a load balancer port mapping; how a particular
    server *should* be port-mapped to a load balancer.

    :ivar int port: The port, which together with the server's IP, specifies
        the service that should be load-balanced by the load balancer.
    :ivar int weight: The weight to be used for certain load-balancing
        algorithms if configured on the load balancer.  Defaults to 1,
        the max is 100.
    :ivar str condition: One of ``ENABLED``, ``DISABLED``, or ``DRAINING`` -
        the default is ``ENABLED``
    :ivar str type: One of ``PRIMARY`` or ``SECONDARY`` - default is ``PRIMARY``
    """


@attributes(["lb_id", "node_id", "address",
             Attribute("drained_at", default_value=0.0, instance_of=float),
             Attribute("connections", default_value=None),
             "config"])
class LBNode(object):
    """
    Information representing an actual node on a load balancer, which is
    an actual, existing, specific port mapping on a load balancer.

    :ivar int lb_id: The Load Balancer ID.
    :ivar int node_id: The ID of the node, which is represents a unique
        combination of IP and port number, on the load balancer.
    :ivar str address: The IP address of the node.  The IP and port form a
        unique mapping on the load balancer, which is assigned a node ID.  Two
        nodes with the same IP and port cannot exist on a single load balancer.
    :ivar float drained_at: EPOCH at which this node was put in DRAINING.
        Will be 0 if node is not DRAINING
    :ivar int connections: The number of active connections on the node - this
        is None by default (the stat is not available yet)

    :ivar config: The configuration for the port mapping
    :type config: :class:`LBConfig`
    """


class ServerState(Names):
    """Constants representing the state cloud servers can have"""
    ACTIVE = NamedConstant()    # corresponds to Nova "ACTIVE"
    ERROR = NamedConstant()     # corresponds to Nova "ERROR"
    BUILD = NamedConstant()     # corresponds to Nova "BUILD" or "BUILDING"
    DRAINING = NamedConstant()  # Autoscale is deleting the server


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
    Create a :obj:`Convergence` that indicates how to transition from the state
    provided by the given parameters to the :obj:`DesiredGroupState` described
    by ``desired_state``.

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

    :rtype: obj:`Convergence`
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

    return Convergence(
        steps=pbag(create_steps
                   + scale_down_steps
                   + delete_error_steps
                   + delete_timeout_steps
                   + lb_converge_steps
                   ))


@attributes(['steps'])
class Convergence(object):
    """
    A :obj:`Convergence` is a set of :class:`ISteps` required to converge a
        ``group_id``.

    :ivar pbag steps: A :obj:`pbag` of :obj:`IStep`s to be performed in
        parallel.
    """


@implementer(IStep)
@attributes(['launch_config'])
class CreateServer(object):
    """
    A server must be created.

    :ivar pmap launch_config: Nova launch configuration.
    """

    def as_request(self):
        """Produce a :obj:`Request` to create a server."""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='POST',
            path='servers',
            data=self.launch_config)


@implementer(IStep)
@attributes(['server_id'])
class DeleteServer(object):
    """
    A server must be deleted.

    :ivar str server_id: a Nova server ID.
    """

    def as_request(self):
        """Produce a :obj:`Request` to delete a server."""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='DELETE',
            path=append_segments('servers', self.server_id))


@implementer(IStep)
@attributes(['server_id', 'key', 'value'])
class SetMetadataItemOnServer(object):
    """
    A metadata key/value item must be set on a server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)
    """
    def as_request(self):
        """Produce a :obj:`Request` to set a metadata item on a server"""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='PUT',
            path=append_segments('servers', self.server_id, 'metadata',
                                 self.key),
            data={'meta': {self.key: self.value}})


@implementer(IStep)
@attributes(['lb_id', 'address_configs'])
class AddNodesToLoadBalancer(object):
    """
    Multiple nodes must be added to a load balancer.

    :param address_configs: A collection of two-tuples of address and
        :obj:`LBConfig`.
    """


@implementer(IStep)
@attributes(['lb_id', 'node_id'])
class RemoveFromLoadBalancer(object):
    """
    A server must be removed from a load balancer.
    """

    def as_request(self):
        """Produce a :obj:`Request` to remove a load balancer node."""
        return Request(
            service=ServiceType.CLOUD_LOAD_BALANCERS,
            method='DELETE',
            path=append_segments('loadbalancers',
                                 str(self.lb_id),
                                 str(self.node_id)))


@implementer(IStep)
@attributes(['lb_id', 'node_id', 'condition', 'weight', 'type'])
class ChangeLoadBalancerNode(object):
    """
    An existing port mapping on a load balancer must have its condition,
    weight, or type modified.
    """

    def as_request(self):
        """Produce a :obj:`Request` to modify a load balancer node."""
        return Request(
            service=ServiceType.CLOUD_LOAD_BALANCERS,
            method='PUT',
            path=append_segments('loadbalancers',
                                 self.lb_id,
                                 'nodes', self.node_id),
            data={'condition': self.condition,
                  'weight': self.weight})


def _rackconnect_bulk_request(lb_node_pairs, method, success_codes):
    """
    Creates a bulk request for RackConnect v3.0 load balancers.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made or broken.
    :param str method: The method of the request ``"DELETE"`` or
        ``"POST"``.
    :param iterable success_codes: Status codes considered successful for this request.
    :return: A bulk RackConnect v3.0 request for the given load balancer,
        node pairs.
    :rtype: :class:`Request`
    """
    return Request(
        service=ServiceType.RACKCONNECT_V3,
        method=method,
        path=append_segments("load_balancer_pools",
                             "nodes"),
        data=[{"cloud_server": {"id": node},
               "load_balancer_pool": {"id": lb}}
              for (lb, node) in lb_node_pairs],
        success_codes=success_codes)


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkAddToRCv3(object):
    """
    Some connections must be made between some combination of servers
    and RackConnect v3.0 load balancers.

    Each connection is independently specified.

    See http://docs.rcv3.apiary.io/#post-%2Fv3%2F{tenant_id}%2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made.
    """

    def as_request(self):
        """
        Produce a :obj:`Request` to add some nodes to some RCv3 load
        balancers.
        """
        return _rackconnect_bulk_request(self.lb_node_pairs, "POST", (201,))


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkRemoveFromRCv3(object):
    """
    Some connections must be removed between some combination of nodes
    and RackConnect v3.0 load balancers.

    See http://docs.rcv3.apiary.io/#delete-%2Fv3%2F{tenant_id}%2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be removed.
    """

    def as_request(self):
        """
        Produce a :obj:`Request` to remove some nodes from some RCv3 load
        balancers.
        """
        return _rackconnect_bulk_request(self.lb_node_pairs, "DELETE", (204,))


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


@attributes(['service', 'method', 'path', 'headers', 'data', 'success_codes'],
            defaults={'headers': None, 'data': None, 'success_codes': (200,)})
class Request(object):
    """
    An object representing a Rackspace API request that must be performed.

    A :class:`Request` only stores information - something else must use the
    information to make an HTTP request, as a :class:`Request` itself has no
    behaviors.

    :ivar ServiceType service: The Rackspace service that the request
        should be sent to. One of the members of :obj:`ServiceType`.
    :ivar bytes method: The HTTP method.
    :ivar bytes path: The path relative to a tenant namespace provided by the
        service.  For example, for cloud servers, this path would be appended
        to something like
        ``https://dfw.servers.api.rackspacecloud.com/v2/010101/`` and would
        therefore typically begin with ``servers/...``.
    :ivar dict headers: a dict mapping bytes to lists of bytes.
    :ivar object data: a Python object that will be JSON-serialized as the body
        of the request.
    :ivar iterable<int> success_codes: The status codes that will be considered
        successful. Defaults to just 200 (OK). Requests that expect other codes,
        such as 201 (Created) for most ``POST`` requests or 204 (No content)
        for most ``DELETE`` requests should specify that through this argument.
    """


def _reqs_to_effect(request_func, conv_requests):
    """Turns a collection of :class:`Request` objects into an effect.

    :param request_func: A pure-http request function, as produced by
        :func:`otter.http.get_request_func`.
    :param conv_requests: Convergence requests to turn into effects.
    :return: An effect which will perform all the requests in parallel.
    :rtype: :class:`Effect`
    """
    effects = [request_func(service_type=r.service,
                            method=r.method,
                            url=r.path,
                            headers=r.headers,
                            data=r.data,
                            success_codes=r.success_codes)
               for r in conv_requests]
    return parallel(effects)
