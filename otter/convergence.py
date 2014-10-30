"""
Convergence.
"""

from __future__ import print_function

from functools import partial
from urllib import urlencode

from effect.retry import retry

from characteristic import attributes, Attribute
from pyrsistent import pbag, freeze, s, pset
from zope.interface import Interface, implementer

from twisted.python.constants import Names, NamedConstant

from toolz.curried import filter, groupby
from toolz.functoolz import compose

from otter.util.http import append_segments
from otter.util.fp import partition_bool, partition_groups
from otter.util.retry import retry_times, exponential_backoff_interval, should_retry_effect


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


def get_all_server_details(request_func, limit=100, clock=None):
    """
    Return all servers of a tenant.

    :param request_func: a request function.
    :param limit: number of servers to fetch *per batch*.

    NOTE: This really screams to be a independent effcloud-type API
    """
    url = append_segments('servers', 'detail')

    def get_server_details(marker):
        # sort based on query name to make the tests predictable
        query = {'limit': limit}
        if marker is not None:
            query.update({'marker': marker})
        urlparams = sorted(query.items(), key=lambda e: e[0])
        eff = retry(
            request_func('GET', '{}?{}'.format(url, urlencode(urlparams))),
            partial(should_retry_effect,
                    retry_times(5), exponential_backoff_interval(2)))
        return eff.on(continue_)

    def continue_(response):
        servers = response['servers']
        if len(servers) < limit:
            return servers
        else:
            more_eff = get_server_details(servers[-1]['id'])
            return more_eff.on(lambda more_servers: servers + more_servers)
    return get_server_details(None)


def get_scaling_group_servers(tenant_id, authenticator, service_name, region,
                              server_predicate=None, clock=None):
    """
    Return tenant's servers that belong to a scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed

    :param server_predicate: `callable` taking single server as arg and returns True
                              if the server should be included, False otherwise
    """

    def has_group_id(s):
        return 'metadata' in s and 'rax:auto_scaling_group_id' in s['metadata']

    def group_id(s):
        return s['metadata']['rax:auto_scaling_group_id']

    server_predicate = server_predicate if server_predicate is not None else lambda s: s
    servers_apply = compose(groupby(group_id), filter(server_predicate), filter(has_group_id))

    d = get_all_server_details(tenant_id, authenticator, service_name, region, clock=clock)
    d.addCallback(servers_apply)
    return d


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
             Attribute('desired_lbs', default_factory=dict, instance_of=dict)])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    :ivar dict desired_lbs: A mapping of load balancer IDs to lists of
        :class:`LBConfig` instances.
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
                       instance_of=NamedConstant),
             Attribute("draining_timeout", default_value=0.0, instance_of=float,
                       exclude_from_cmp=True)])
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

    TODO: this is not the ideal place for ``draining_timeout``, since
    :class:`LBConfig` is more about what node on a CLB should look like.
    And :class:`LBConfig` may not be applicable to a hardware LB.
    So `draining_timeout` is here until other load balancer requirements are
    understood and a better place is found for it.
    :ivar float draining_timeout: Number of seconds node should be in DRAINING
        state before being removed
    """


@attributes(["lb_id", "node_id", "address",
             Attribute("drained_at", default_value=0.0, instance_of=float), "config"])
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

    :ivar config: The configuration for the port mapping
    :type config: :class:`LBConfig`
    """


ACTIVE = 'ACTIVE'
ERROR = 'ERROR'
BUILD = 'BUILD'


def _converge_lb_state(desired_lb_state, current_lb_state, ip_address):
    """
    Produce a series of steps to converge a server's current load balancer
    state towards its desired load balancer state.

    The server will be removed from any extra load balancers the server
    is currently on, and it will be added on the correct port, with the correct
    weight, and correct status, to the desired load balancers.

    :param dict desired_lb_state: As per :obj:`DesiredGroupState`.desired_lbs
    :param list current_lb_state: `list` of :obj:`LBNode`
    :param str ip_address: the IP address of the server to converge

    Note: this supports user customizable types (e.g. PRIMARY or SECONDARY), but
    in practice it should probably only be added as PRIMARY.  SECONDARY can only
    be used if load balancer health monitoring is enabled, and would be used as
    backup servers anyway.
    """
    desired = {
        (lb_id, config.port): config
        for lb_id, configs in desired_lb_state.items()
        for config in configs}
    current = {
        (node.lb_id, node.config.port): node
        for node in current_lb_state}
    desired_idports = set(desired)
    current_idports = set(current)

    adds = [
        AddNodesToLoadBalancer(
            lb_id=lb_id,
            address_configs=s((ip_address, desired[lb_id, port])))
        for lb_id, port in desired_idports - current_idports]
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


def converge(desired_state, servers_with_cheese, load_balancer_contents, now,
             timeout=3600):
    """
    Create a :obj:`Convergence` that indicates how to transition from the state
    provided by the given parameters to the :obj:`DesiredGroupState` described
    by ``desired_state``.

    :param DesiredGroupState desired_state: The desired group state.
    :param list servers_with_cheese: a list of :obj:`NovaServer` instances.
        This must only contain servers that are being managed for the specified
        group.
    :param load_balancer_contents: a list of :obj:`LBNode` instances.  This must
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
    servers_in_error, servers_in_active, servers_in_build = partition_groups(
        lambda s: s.state, newest_to_oldest, [ERROR, ACTIVE, BUILD])

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

    # delete over capacity, starting with building, then active,
    # preferring older
    servers_to_delete = (servers_in_active + waiting_for_build)[desired_state.desired:]
    delete_steps = (
        [DeleteServer(server_id=server.id) for server in servers_to_delete] +
        [RemoveFromLoadBalancer(lb_id=lb_node.lb_id,
                                node_id=lb_node.node_id)
         for server in servers_to_delete
         for lb_node in lbs_by_address.get(server.servicenet_address, [])])

    # delete all servers in error.
    delete_error_steps = (
        [DeleteServer(server_id=server.id) for server in servers_in_error] +
        [RemoveFromLoadBalancer(lb_id=lb_node.lb_id,
                                node_id=lb_node.node_id)
         for server in servers_in_error
         for lb_node in lbs_by_address.get(server.servicenet_address, [])])

    # converge all the servers that remain to their desired load balancer state
    new_active_servers = filter(lambda s: s not in servers_to_delete,
                                servers_in_active)
    lb_converge_steps = [
        step
        for server in new_active_servers
        for step in _converge_lb_state(
            desired_state.desired_lbs,
            lbs_by_address.get(server.servicenet_address, []),
            server.servicenet_address)
        if server.servicenet_address]

    return Convergence(
        steps=pbag(create_steps
                   + delete_steps
                   + delete_error_steps
                   + delete_timeout_steps
                   + lb_converge_steps
                   ))


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

    Currently batches up groups of :obj:`AddNodesToLoadBalancer` steps into
    one per load balancer.

    :param pbag steps: Collection of steps.
    :return: a pbag of steps.
    """
    lb_adds, other = partition_bool(
        lambda s: type(s) is AddNodesToLoadBalancer,
        steps)
    merged_adds = _optimize_lb_adds(lb_adds)
    return pbag(merged_adds + other)


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


class ServiceType(Names):
    """Constants representing Rackspace cloud services."""
    CLOUD_SERVERS = NamedConstant()
    CLOUD_LOAD_BALANCERS = NamedConstant()


@attributes(['service', 'method', 'path', 'headers', 'data'],
            defaults={'headers': None, 'data': None})
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
    """
