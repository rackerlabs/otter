"""Code related to gathering data to inform convergence."""
import json
from collections import defaultdict
from urllib import urlencode

from effect import parallel

from pyrsistent import pmap

from toolz.curried import filter, groupby, map
from toolz.dicttoolz import get_in
from toolz.functoolz import compose, identity

from otter.constants import ServiceType
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    NovaServer,
    ServerState)
from otter.http import service_request
from otter.indexer import atom
from otter.util.http import append_segments
from otter.util.retry import (
    exponential_backoff_interval, retry_effect, retry_times)
from otter.util.timestamp import timestamp_to_epoch


def get_all_server_details(batch_size=100):
    """
    Return all servers of a tenant.

    :param batch_size: number of servers to fetch *per batch*.
    :return: list of server objects as returned by Nova.

    NOTE: This really screams to be a independent fxcloud-type API
    """
    url = append_segments('servers', 'detail')

    def get_server_details(marker):
        # sort based on query name to make the tests predictable
        query = {'limit': batch_size}
        if marker is not None:
            query.update({'marker': marker})
        urlparams = sorted(query.items())
        eff = retry_effect(
            service_request(
                ServiceType.CLOUD_SERVERS,
                'GET', '{}?{}'.format(url, urlencode(urlparams))),
            retry_times(5), exponential_backoff_interval(2))
        return eff.on(continue_)

    def continue_(result):
        _response, body = result
        servers = body['servers']
        if len(servers) < batch_size:
            return servers
        else:
            more_eff = get_server_details(servers[-1]['id'])
            return more_eff.on(lambda more_servers: servers + more_servers)

    return get_server_details(marker=None)


def _discard_response((response, body)):
    """
    Takes a response, body tuple and discards the response.
    """
    return body


def get_scaling_group_servers(server_predicate=identity):
    """
    Return tenant's servers that belong to a scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed

    :param server_predicate: function of server -> bool that determines whether
        the server should be included in the result.
    :return: dict mapping group IDs to lists of Nova servers.
    """

    def has_group_id(s):
        return 'metadata' in s and 'rax:auto_scaling_group_id' in s['metadata']

    def group_id(s):
        return s['metadata']['rax:auto_scaling_group_id']

    servers_apply = compose(groupby(group_id),
                            filter(server_predicate),
                            filter(has_group_id))

    eff = get_all_server_details()
    return eff.on(servers_apply)


def get_clb_contents():
    """
    Get Rackspace Cloud Load Balancer contents as list of `CLBNode`.
    """

    def lb_req(method, url, json_response=True):
        """Make a request to the LB service with retries."""
        return retry_effect(
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                method, url, json_response=json_response),
            retry_times(5), exponential_backoff_interval(2))

    def _lb_path(lb_id):
        """Return the URL path to lb with given id's nodes."""
        return append_segments('loadbalancers', str(lb_id), 'nodes')

    def fetch_nodes(result):
        _response, body = result
        lbs = body['loadBalancers']
        lb_ids = [lb['id'] for lb in lbs]
        lb_reqs = [lb_req('GET', _lb_path(lb_id)).on(_discard_response)
                   for lb_id in lb_ids]
        return parallel(lb_reqs).on(lambda all_nodes: (lb_ids, all_nodes))

    def fetch_drained_feeds((ids, all_lb_nodes)):
        nodes = [
            CLBNode(
                node_id=str(node['id']),
                address=node['address'],
                description=CLBDescription(
                    lb_id=str(_id),
                    port=node['port'],
                    weight=node['weight'],
                    condition=CLBNodeCondition.lookupByName(node['condition']),
                    type=CLBNodeType.lookupByName(node['type'])))
            for _id, nodes in zip(ids, all_lb_nodes) for node in nodes]
        draining = [n for n in nodes
                    if n.description.condition == CLBNodeCondition.DRAINING]
        return parallel(
            [lb_req(
                'GET',
                append_segments(
                    'loadbalancers',
                    str(n.description.lb_id),
                    'nodes',
                    '{}.atom'.format(n.node_id)),
                json_response=False).on(_discard_response)
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
    # it was draining operation. May need to look at all entries in reverse
    # order and check for draining operation. This could include paging to
    # further entries
    entry = atom.entries(atom.parse(feed))[0]
    summary = atom.summary(entry)
    if 'Node successfully updated' in summary and 'DRAINING' in summary:
        return timestamp_to_epoch(atom.updated(entry))
    else:
        raise ValueError('Unexpected summary: {}'.format(summary))


def _private_ipv4_addresses(server):
    """
    Get all private IPv4 addresses from the addresses section of a server.

    :param dict server: A server dict.
    :return: List of IP addresses as strings.
    """
    private_addresses = get_in(["addresses", "private"], server, [])
    return [addr['addr'] for addr in private_addresses if addr['version'] == 4]


def _servicenet_address(server):
    """
    Find the ServiceNet address for the given server.
    """
    return next((ip for ip in _private_ipv4_addresses(server)
                 if ip.startswith("10.")), "")


_key_prefix = 'rax:autoscale:lb:'


def _lb_configs_from_metadata(server):
    """
    Construct a mapping of load balancer ID to :class:`ILBDescription` based
    on the server metadata.
    """
    desired_lbs = defaultdict(list)

    # throw away any value that is malformed

    def parse_config(config, key):
        if config.get('type') != 'RackConnectV3':
            lbid = k[len(_key_prefix):]
            try:
                desired_lbs[lbid].append(
                    CLBDescription(lb_id=lbid, port=config['port']))
            except (KeyError, TypeError):
                pass

    for k in server.get('metadata', {}):
        if k.startswith(_key_prefix):
            try:
                configs = json.loads(server['metadata'][k])
                for config in configs:
                    parse_config(config, k)
            except (ValueError, AttributeError):
                pass

    return pmap(desired_lbs)


def to_nova_server(server_json):
    """
    Convert from JSON format to :obj:`NovaServer` instance.
    """
    return NovaServer(id=server_json['id'],
                      state=ServerState.lookupByName(server_json['status']),
                      created=timestamp_to_epoch(server_json['created']),
                      image_id=server_json.get('image', {}).get('id'),
                      flavor_id=server_json['flavor']['id'],
                      desired_lbs=_lb_configs_from_metadata(server_json),
                      servicenet_address=_servicenet_address(server_json))


def get_all_convergence_data(
        group_id,
        get_scaling_group_servers=get_scaling_group_servers,
        get_clb_contents=get_clb_contents):
    """
    Gather all data relevant for convergence, in parallel where
    possible.

    Returns an Effect of ([NovaServer], [LBNode]).
    """
    eff = parallel(
        [get_scaling_group_servers()
         .on(lambda servers: servers.get(group_id, []))
         .on(map(to_nova_server)).on(list),
         get_clb_contents()]
    ).on(tuple)
    return eff
