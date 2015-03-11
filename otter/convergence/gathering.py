"""Code related to gathering data to inform convergence."""
from functools import partial
from urllib import urlencode

from effect import catch, parallel

from toolz.curried import filter, groupby, keyfilter, map
from toolz.dicttoolz import get_in
from toolz.functoolz import compose, identity
from toolz.itertoolz import concat

from otter.auth import NoSuchEndpoint
from otter.constants import ServiceType
from otter.convergence.model import (
    CLBDescription,
    CLBNode,
    CLBNodeCondition,
    CLBNodeType,
    NovaServer,
    RCv3Description,
    RCv3Node,
    group_id_from_metadata)
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
        return 'metadata' in s and isinstance(s['metadata'], dict)

    def group_id(s):
        return group_id_from_metadata(s['metadata'])

    servers_apply = compose(keyfilter(lambda k: k is not None),
                            groupby(group_id),
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


def get_rcv3_contents():
    """
    Get Rackspace Cloud Load Balancer contents as list of `RCv3Node`.
    """
    eff = retry_effect(
        service_request(ServiceType.RACKCONNECT_V3,
                        'GET', 'load_balancer_pools'),
        retry_times(5), exponential_backoff_interval(2))

    def on_listing_pools(lblist_result):
        _, body = lblist_result
        return parallel([
            retry_effect(
                service_request(ServiceType.RACKCONNECT_V3, 'GET',
                                append_segments('load_balancer_pools',
                                                lb_pool['id'], 'nodes')),
                retry_times(5), exponential_backoff_interval(2)
            ).on(
                partial(on_listing_nodes,
                        RCv3Description(lb_id=lb_pool['id'])))

            for lb_pool in body
        ])

    def on_listing_nodes(rcv3_description, lbnodes_result):
        _, body = lbnodes_result
        return [
            RCv3Node(node_id=node['id'], description=rcv3_description,
                     cloud_server_id=get_in(('cloud_server', 'id'), node))
            for node in body
        ]

    return eff.on(on_listing_pools).on(
        success=compose(list, concat),
        error=catch(NoSuchEndpoint, lambda _: []))


def get_all_convergence_data(
        group_id,
        get_scaling_group_servers=get_scaling_group_servers,
        get_clb_contents=get_clb_contents,
        get_rcv3_contents=get_rcv3_contents):
    """
    Gather all data relevant for convergence, in parallel where
    possible.

    Returns an Effect of ([NovaServer], [LBNode]).
    """
    eff = parallel(
        [get_scaling_group_servers()
         .on(lambda servers: servers.get(group_id, []))
         .on(map(NovaServer.from_server_details_json)).on(list),
         get_clb_contents(),
         get_rcv3_contents()]
    ).on(lambda (servers, clb, rcv3): (servers, list(concat([clb, rcv3]))))
    return eff
