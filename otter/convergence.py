"""
Convergence.
"""

from functools import partial
from urllib import urlencode

import treq

from twisted.internet import defer

from characteristic import attributes
from pyrsistent import pbag, freeze
from zope.interface import Interface, implementer

from toolz.curried import filter, groupby
from toolz.functoolz import compose

from otter.log import log as default_log
from otter.util.http import append_segments, check_success, headers
from otter.util.fp import partition_bool, partition_groups
from otter.util.retry import retry, retry_times, exponential_backoff_interval
# TODO: I hate including this!
from otter.worker.launch_server_v1 import public_endpoint_url


@defer.inlineCallbacks
def get_all_server_details(tenant_id, authenticator, service_name, region,
                           limit=100, clock=None, _treq=None):
    """
    Return all servers of a tenant
    TODO: service_name is possibly internal to this function but I don't want to pass config here?
    NOTE: This really screams to be a independent txcloud-type API
    """
    token, catalog = yield authenticator.authenticate_tenant(tenant_id, log=default_log)
    endpoint = public_endpoint_url(catalog, service_name, region)
    url = append_segments(endpoint, 'servers', 'detail')
    query = {'limit': limit}
    all_servers = []

    if clock is None:  # pragma: no cover
        from twisted.internet import reactor as clock

    if _treq is None:  # pragma: no cover
        _treq = treq

    def fetch(url, headers):
        d = _treq.get(url, headers=headers)
        d.addCallback(check_success, [200], _treq=_treq)
        d.addCallback(_treq.json_content)
        return d

    while True:
        # sort based on query name to make the tests predictable
        urlparams = sorted(query.items(), key=lambda e: e[0])
        d = retry(partial(fetch, '{}?{}'.format(url, urlencode(urlparams)), headers(token)),
                  can_retry=retry_times(5),
                  next_interval=exponential_backoff_interval(2), clock=clock)
        servers = (yield d)['servers']
        all_servers.extend(servers)
        if len(servers) < limit:
            break
        query.update({'marker': servers[-1]['id']})

    defer.returnValue(all_servers)


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
        Create a request for performing this step.
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


@attributes(['id', 'state', 'created'])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    """


ACTIVE = 'ACTIVE'
ERROR = 'ERROR'
BUILD = 'BUILD'


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
    delete_steps = [DeleteServer(server_id=server.id)
                    for server in servers_to_delete]

    # delete all servers in error.
    delete_error_steps = [DeleteServer(server_id=server.id)
                          for server in servers_in_error]

    return Convergence(
        steps=pbag(create_steps
                   + delete_steps
                   + delete_error_steps
                   + delete_timeout_steps
                   ))


@attributes(['steps'])
class Convergence(object):
    """
    A :obj:`Convergence` is a set of steps required to converge a ``group_id``.

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
