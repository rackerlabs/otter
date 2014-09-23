
"""
Convergence.
"""

from functools import partial
from urllib import urlencode

import treq

from twisted.internet import defer

from characteristic import attributes
from zope.interface import Interface, implementer

from toolz.curried import filter, groupby

from otter.log import log as default_log
from otter.util.http import append_segments, check_success, headers
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

    if clock is None:
        from twisted.internet import reactor
        clock = reactor

    if _treq is None:
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


def get_scaling_group_servers(tenant_id, authenticator, service_name, region, clock=None):
    """
    Return tenant's servers that belong to a scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed
    """

    def group_id(server_details):
        m = server_details.get('metadata', {})
        return m.get('rax:auto_scaling_group_id', 'nogroup')

    def del_nogroup(grouped_servers):
        if 'nogroup' in grouped_servers:
            del grouped_servers['nogroup']
        return grouped_servers

    valid_statuses = ('ACTIVE', 'BUILD', 'HARD_REBOOT', 'MIGRATION', 'PASSWORD',
                      'RESIZE', 'REVERT_RESIZE', 'VERIFY_RESIZE')

    d = get_all_server_details(tenant_id, authenticator, service_name, region, clock=clock)
    # filter out invalid servers
    d.addCallback(filter(lambda s: s['status'] in valid_statuses))
    # group based on scaling_group_id
    d.addCallback(groupby(group_id))
    # remove servers not belonging to any group
    d.addCallback(del_nogroup)
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


@attributes(['id', 'launch_config', 'desired'])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar str id: The group's ID.
    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
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
