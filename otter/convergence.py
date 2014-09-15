"""
Convergence.
"""

from collections import Counter

from characteristic import attributes
from zope.interface import Interface, implementer
from toolz.itertoolz import groupby


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_request():
        """
        Create a request for performing this step.
        """


@attributes(['id', 'launch_config', 'desired'])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar str id: The group's ID.
    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    """


@attributes(['id', 'state', 'created'])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    """


def converge(desired_state, servers_with_cheese, load_balancer_contents, now):
    """
    Create a :obj:`Convergence` that indicates how to transition from the state
    provided by the given parameters to the :obj:`DesiredGroupState` described
    by ``desired_state``.

    :param DesiredGroupState desired_state: The desired group state.
    :param dict servers_with_cheese: a dictionary mapping server IDs to nova
        server information (the JSON-serializable dictionary returned from a
        ``.../servers/detail/`` request)
    :param dict load_balancer_contents: a dictionary mapping load balancer IDs
        to lists of 2-tuples of (IP address, loadbalancer node ID).
    :param float now: number of seconds since the POSIX epoch indicating the
        time at which the convergence was requested.

    :rtype: obj:`Convergence`
    """
    servers_by_state = groupby(lambda s: s.state, servers_with_cheese)
    servers_in_error = servers_by_state.get('ERROR', [])
    servers_in_active = servers_by_state.get('ACTIVE', [])
    servers_in_building = servers_by_state.get('BUILDING', [])
    create_server = CreateServer(launch_config=desired_state.launch_config)
    create_steps = [create_server] * (desired_state.desired
                                      - (len(servers_in_active)
                                         + len(servers_in_building)))
    newest_to_oldest = sorted(servers_with_cheese,
                              key=lambda s: -s.created)
    servers_to_delete = newest_to_oldest[desired_state.desired:]
    delete_steps = [DeleteServer(server_id=server.id)
                    for server in servers_to_delete]
    delete_error_steps = [DeleteServer(server_id=server.id)
                          for server in servers_in_error]
    return Convergence(
        group_id=desired_state.id,
        steps=Counter(create_steps + delete_steps + delete_error_steps))


@attributes(['steps', 'group_id'])
class Convergence(object):
    """
    A :obj:`Convergence` is a set of steps required to converge a ``group_id``.

    :ivar set steps: A set of :obj:`IStep`s to be performed in parallel.
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
@attributes(['loadbalancer_id', 'node_id', 'condition', 'weight'])
class ChangeLoadBalancerNode(object):
    """
    An existing port mapping on a load balancer must have its condition or
    weight modified.
    """


CLOUD_SERVERS = 'cloudServersOpenStack'
CLOUD_LOAD_BALANCERS = 'cloudLoadBalancers'


@attributes(['service', 'method', 'path', 'headers', 'data'])
class Request(object):
    """
    A Rackspace API request must be performed.

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
