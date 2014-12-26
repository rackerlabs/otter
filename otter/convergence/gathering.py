"""Code related to gathering data to inform convergence."""

from collections import defaultdict
from urllib import urlencode

from effect import parallel

from toolz.curried import filter, groupby
from toolz.dicttoolz import get_in
from toolz.functoolz import compose, identity

from otter.constants import ServiceType
from otter.convergence.model import (
    LBConfig,
    LBNode,
    CLBNodeCondition,
    CLBNodeType,
    NovaServer,
    ServerState)
from otter.indexer import atom
from otter.util.http import append_segments
from otter.util.retry import exponential_backoff_interval, retry_effect, retry_times
from otter.util.timestamp import timestamp_to_epoch


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


def get_clb_contents(request_func):
    """
    Get Rackspace Cloud Load Balancer contents as list of `LBNode`.

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
        return parallel(
            [lb_req('GET', append_segments('loadbalancers', str(lb_id), 'nodes'))
             for lb_id in lb_ids]).on(lambda all_nodes: (lb_ids, all_nodes))

    def fetch_drained_feeds((ids, all_lb_nodes)):
        nodes = [LBNode(lb_id=_id, node_id=node['id'], address=node['address'],
                        config=LBConfig(port=node['port'], weight=node['weight'],
                                        condition=CLBNodeCondition.lookupByName(node['condition']),
                                        type=CLBNodeType.lookupByName(node['type'])))
                 for _id, nodes in zip(ids, all_lb_nodes)
                 for node in nodes]
        draining = [n for n in nodes if n.config.condition == CLBNodeCondition.DRAINING]
        return parallel(
            [lb_req(
                'GET',
                append_segments('loadbalancers', str(n.lb_id), 'nodes',
                                '{}.atom'.format(n.node_id)),
                json_response=False)
             for n in draining]).on(lambda feeds: (nodes, draining, feeds))

    def fill_drained_at((nodes, draining, feeds)):
        for node, feed in zip(draining, feeds):
            node.drained_at = extract_CLB_drained_at(feed)
        return nodes

    return lb_req('GET', 'loadbalancers').on(
        fetch_nodes).on(fetch_drained_feeds).on(fill_drained_at)


def extract_CLB_drained_at(feed):
    """
    Extract time when node was changed to DRAINING from a CLB atom feed.

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
