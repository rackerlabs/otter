# -*- test-case-name: otter.test.test_convergence -*-
"""
Convergence.
"""

from urllib import urlencode
from itertools import izip as zip
from operator import itemgetter
import time
from collections import defaultdict

from characteristic import attributes, Attribute
from effect import parallel
from pyrsistent import pbag, freeze, s, pset
from zope.interface import Interface, implementer

from twisted.python.constants import Names, NamedConstant

import effect

from toolz.curried import filter, groupby, map
from toolz.functoolz import compose, identity
from toolz.itertoolz import concat, concatv, mapcat
from toolz.dicttoolz import get_in

from otter.constants import ServiceType
from otter.util.http import append_segments
from otter.util.fp import partition_bool, partition_groups
from otter.util.retry import retry_times, exponential_backoff_interval, retry_effect
from otter.util.timestamp import timestamp_to_epoch
from otter.indexer import atom

# radix in-development imports

from otter.convergence.planning import converge, _remove_from_lb_with_draining, _converge_lb_state
from otter.convergence.steps import AddNodesToLoadBalancer, BulkAddToRCv3, BulkRemoveFromRCv3, CreateServer, DeleteServer, RemoveFromLoadBalancer, ChangeLoadBalancerNode, SetMetadataItemOnServer, Request, Convergence
from otter.convergence.model import NodeCondition, NodeType, ServerState


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


def to_nova_server(server_json):
    """
    Convert from JSON format to :obj:`NovaServer` instance
    """
    ips = get_in(['addresses', 'private'], server_json, default=[])
    ip = ''
    if len(ips) > 0:
        ip = [addr['addr'] for addr in ips if addr['version'] == 4][0]
    return NovaServer(id=server_json['id'], state=ServerState.lookupByName(server_json['state']),
                      created=timestamp_to_epoch(server_json['created']),
                      servicenet_address=ip)


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
        return timestamp_to_epoch(atom.updated(entry))
    else:
        raise ValueError('Unexpected summary: {}'.format(summary))


def get_load_balancer_contents(request_func):
    """
    Get load balancer contents as list of `LBNode`

    :param request_func: A tenant-bound, CLB-bound, auth-retry based request function
    """

    def lb_req(method, url, json_response=True):
        """Make a request to the LB service with retries."""
        return retry_effect(
            request_func(
                ServiceType.CLOUD_LOAD_BALANCERS,
                method, url, json_response=json_response),
            retry_times(5), exponential_backoff_interval(2))

    def fetch_nodes(lbs):
        lb_ids = [lb['id'] for lb in lbs]
        return effect.parallel(
            [lb_req('GET', append_segments('loadbalancers', str(lb_id), 'nodes'))
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
            [lb_req(
                'GET',
                append_segments('loadbalancers', str(n.lb_id), 'nodes',
                                '{}.atom'.format(n.node_id)),
                json_response=False)
             for n in draining]).on(lambda feeds: (nodes, draining, feeds))

    def fill_drained_at((nodes, draining, feeds)):
        for node, feed in zip(draining, feeds):
            node.drained_at = extract_drained_at(feed)
        return nodes

    return lb_req('GET', 'loadbalancers').on(
        fetch_nodes).on(fetch_drained_feeds).on(fill_drained_at)




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


def json_to_LBConfigs(lbs_json):
    """
    Convert load balancer config from JSON to :obj:`LBConfig`

    :param list lbs_json: List of load balancer configs
    :return: `dict` of LBid -> [LBConfig] mapping

    NOTE: Currently ignores RackConnectV3 configs. Will add them when it gets
    implemented in convergence
    """
    lbd = defaultdict(list)
    for lb in lbs_json:
        if lb.get('type') != 'RackConnectV3':
            lbd[lb['loadBalancerId']].append(LBConfig(port=lb['port']))
    return lbd


def execute_convergence(request_func, group_id, desired, launch_config,
                        get_servers=get_scaling_group_servers,
                        get_lb=get_load_balancer_contents):
    """
    Execute convergence. This function will do following:
    1. Get state of the nova, CLB and RCv3.
    2. Call `converge` with above info and get steps to execute
    3. Execute these steps
    This is in effect single cycle execution. A layer above this is expected
    to keep calling this until this function returns False

    :param request_func: Tenant bound request function
    :param bytes group_id: Tenant's group
    :param int desired: Group's desired capacity
    :param dict launch_config: Group's launch config as per
                              :obj:`otter.json_schema.group_schemas.launch_config`
    :param callable get_servers: Optional arg to get scaling group servers useful for testing
    :param callable get_lb: Optional arg to get load balancer info useful for testing

    :return: Effect with Bool specifying if it should be called again
    :rtype: :class:`effect.Effect`
    """
    eff = effect.parallel(
        [get_servers(request_func).on(itemgetter(group_id)).on(map(to_nova_server)),
         get_lb(request_func)])

    lbs = json_to_LBConfigs(launch_config['args']['loadBalancers'])
    desired_state = DesiredGroupState(launch_config={'server': launch_config['args']['server']},
                                      desired=desired, desired_lbs=lbs)

    conv_eff = eff.on(lambda (servers, lb_nodes): converge(desired_state, servers, lb_nodes,
                                                           time.time()))
    # TODO: Do request specific throttling. For ex create only 3 servers at a time
    return conv_eff.on(lambda c: optimize_steps(c.steps)).on(
        lambda steps: _reqs_to_effect(request_func, [s.as_request() for s in steps])).on(bool)


def tenant_is_enabled(tenant_id, get_config_value):
    """
    Feature-flag test: is the given tenant enabled for convergence?

    :param str tenant_id: A tenant's ID, which may or may not be present in the
        "convergence-tenants" portion of the configuration file.
    :param callable get_config_value: config key -> config value.
    """
    enabled_tenant_ids = get_config_value("convergence-tenants")
    return (tenant_id in enabled_tenant_ids)
