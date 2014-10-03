"""
Convergence.
"""

from characteristic import attributes, Attribute
from pyrsistent import pbag, freeze
from zope.interface import Interface, implementer

from otter.util.fp import partition_bool, partition_groups


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_request():
        """
        Create a :class:`Request` object that contains relevant information for
        performing a HTTP request
        """


@attributes(['launch_config', 'desired'])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    """

    def __init__(self):
        self.launch_config = freeze(self.launch_config)


@attributes(['id', 'state', 'created',
             Attribute('private_address', default_value='', instance_of=str),
             Attribute('desired_lbs', default_value={}, instance_of=dict),
             Attribute('current_lbs', default_value={}, instance_of=dict)])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    :ivar dict desired_lbs: Dictionary with keys of type
        ``(loadbalancer_id, port)`` mapped to :class:`DesiredLBConfig`
    :ivar dict current_lbs: Dictionary with keys of type
        ``(loadbalancer_id, port)`` mapped to :class:`ActualLBConfig`
    """


@attributes(["lb_id", "port",
             Attribute("weight", default_value=1, instance_of=int),
             Attribute("condition", default_value="ENABLED", instance_of=str),
             Attribute("type", default_value="PRIMARY", instance_of=str)])
class LBConfig(object):
    """
    Information representing a load balancer port mapping; how a particular
    server *should* be port-mapped to a particular load balancer.

    :ivar int lb_id: The load balancer ID.
    :ivar int port: The port, which together with the server's IP, specifies
        the service that should be load-balanced by the load balancer.
    :ivar int weight: The weight to be used for certain load-balancing
        algorithms if configured on the load balancer.  Defaults to 1,
        the max is 100.
    :ivar str condition: One of ``ENABLED``, ``DISABLED``, or ``DRAINING`` -
        the default is ``ENABLED``
    :ivar str type: One of ``PRIMARY`` or ``SECONDARY`` - default is ``PRIMARY``
    """


@attributes(["node_id", "address", "config"])
class LBNode(object):
    """
    Information representing an actual node on a load balancer, which is
    an actual, existing, specific port mapping on a load balancer.

    :ivar int node_id: The ID of the node, which is represents a unique
        combination of IP and port number, on the load balancer.
    :ivar int address: The IP address, which together with the port, specifies
        the service that should be load-balanced by the load balancer.

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
    currently be on, and it will be added on the correct port, with the correct
    weight, and correct status, to the desired load balancers.

    Both ``desired_lb_state`` and ``current_lb_state`` are dictionaries keyed
    by a tuple of ``(loadbalancer_id, port)``.

    Note: this supports user customizable types (e.g. PRIMARY or SECONDARY), but
    in practice it should probably only be added as PRIMARY.  SECONDARY can only
    be used if load balancer health monitoring is enabled, and would be used as
    backup servers anyway.
    """
    for key, desired_config in desired_lb_state.iteritems():
        lb_node = current_lb_state.get(key)

        if lb_node is None:
            yield AddToLoadBalancer(loadbalancer_id=desired_config.lb_id,
                                    address=ip_address,
                                    port=desired_config.port,
                                    condition=desired_config.condition,
                                    weight=desired_config.weight,
                                    type=desired_config.type)

        elif desired_config != lb_node.config:
            yield ChangeLoadBalancerNode(loadbalancer_id=desired_config.lb_id,
                                         node_id=lb_node.node_id,
                                         condition=desired_config.condition,
                                         weight=desired_config.weight,
                                         type=desired_config.type)

    undesirables = (item for item in current_lb_state.iteritems()
                    if item[0] not in desired_lb_state)

    for key, current in undesirables:
        yield RemoveFromLoadBalancer(loadbalancer_id=current.config.lb_id,
                                     node_id=current.node_id)


def converge(desired_state, servers_with_cheese, load_balancer_contents, now,
             timeout=3600):
    """
    Create a :obj:`Convergence` that indicates how to transition from the state
    provided by the given parameters to the :obj:`DesiredGroupState` described
    by ``desired_state``.

    :param DesiredGroupState desired_state: The desired group state.
    :param list servers_with_cheese: a list of of :obj:`NovaServer` instances.
        This must only contain servers that are being managed for the specified
        group.
    :param dict load_balancer_contents: a dictionary mapping load balancer IDs
        to lists of 2-tuples of (IP address, loadbalancer node ID).
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.
    :param float timeout: Number of seconds after which we will delete a server
        in BUILD.

    :rtype: obj:`Convergence`
    """
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
        [RemoveFromLoadBalancer(lb_config.lb_id, lb_config.node_id)
         for server in servers_to_delete
         for lb_config in server.current_lbs])

    # delete all servers in error.
    delete_error_steps = (
        [DeleteServer(server_id=server.id) for server in servers_in_error] +
        [RemoveFromLoadBalancer(lb_config.lb_id, lb_config.node_id)
         for server in servers_in_error
         for lb_config in server.current_lbs])

    # converge all the servers that remain to their desired load balancer state
    lb_converge_steps = [
        step
        for server in servers_in_active
        for step in _converge_lb_state(server.desired_lbs,
                                       server.current_lbs,
                                       server.private_address)
        if server not in servers_to_delete and server.private_address]

    return Convergence(
        steps=pbag(create_steps
                   + delete_steps
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

    :ivar dict launch_config: Nova launch configuration.
    """


@implementer(IStep)
@attributes(['server_id'])
class DeleteServer(object):
    """
    A server must be deleted.

    :ivar str server_id: a Nova server ID.
    """


@implementer(IStep)
@attributes(['loadbalancer_id', 'address', 'port', 'condition', 'weight',
             'type'])
class AddToLoadBalancer(object):
    """
    A server must be added to a load balancer.
    """


@implementer(IStep)
@attributes(['loadbalancer_id', 'node_id'])
class RemoveFromLoadBalancer(object):
    """
    A server must be removed from a load balancer.
    """


@implementer(IStep)
@attributes(['loadbalancer_id', 'node_id', 'condition', 'weight', 'type'])
class ChangeLoadBalancerNode(object):
    """
    An existing port mapping on a load balancer must have its condition,
    weight, or type modified.
    """


CLOUD_SERVERS = 'cloudServersOpenStack'
CLOUD_LOAD_BALANCERS = 'cloudLoadBalancers'


@attributes(['service', 'method', 'path', 'headers', 'data'])
class Request(object):
    """
    An object representing a Rackspace API request that must be performed.

    A :class:`Request` only stores information - something else must use the
    information to make an HTTP request, as a :class:`Request` itself has no
    behaviors.

    :ivar str service: The name of the Rackspace service; either
        :obj:`CLOUD_SERVERS` or :obj:`CLOUD_LOAD_BALANCERS`.
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
