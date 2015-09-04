"""Code related to gathering data to inform convergence."""
from functools import partial

from effect import catch, parallel
from effect.do import do, do_return

from toolz.curried import filter, groupby, keyfilter, map
from toolz.dicttoolz import assoc, get_in, merge
from toolz.functoolz import compose, curry, identity
from toolz.itertoolz import concat

from otter.auth import NoSuchEndpoint
from otter.cloud_client import (
    CLBNotFoundError,
    get_clb_node_feed,
    get_clb_nodes,
    get_clbs,
    list_servers_details_all,
    service_request)
from otter.constants import ServiceType
from otter.convergence.model import (
    CLBNode,
    CLBNodeCondition,
    NovaServer,
    RCv3Description,
    RCv3Node,
    group_id_from_metadata)
from otter.indexer import atom
from otter.models.cass import CassScalingGroupServersCache
from otter.util.fp import assoc_obj
from otter.util.http import append_segments
from otter.util.retry import (
    exponential_backoff_interval, retry_effect, retry_times)
from otter.util.timestamp import timestamp_to_epoch


def _retry(eff):
    """Retry an effect with a common policy."""
    return retry_effect(
        eff, retry_times(5), exponential_backoff_interval(2))


def get_all_server_details(changes_since=None, batch_size=100):
    """
    Return all servers of a tenant.

    :param datetime changes_since: Get changes since this time. Must be UTC
    :param int batch_size: number of servers to fetch *per batch*.
    :return: list of server objects as returned by Nova.

    NOTE: This really screams to be a independent fxcloud-type API
    """
    query = {'limit': [str(batch_size)]}
    if changes_since is not None:
        query['changes-since'] = ['{0}Z'.format(changes_since.isoformat())]

    return list_servers_details_all(query)


def get_all_scaling_group_servers(changes_since=None,
                                  server_predicate=identity):
    """
    Return tenant's servers that belong to any scaling group as
    {group_id: [server1, server2]} ``dict``. No specific ordering is guaranteed

    :param datetime changes_since: Get server since this time. Must be UTC
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

    return get_all_server_details(changes_since).on(servers_apply)


def mark_deleted_servers(old, new):
    """
    Given dictionaries containing old and new servers, return a list of all
    servers, with the deleted ones annotated with a status of DELETED.

    :param list old: List of old servers
    :param list new: List of latest servers
    :return: List of updated servers
    """

    def sdict(servers):
        return {s['id']: s for s in servers}

    old = sdict(old)
    new = sdict(new)
    deleted_ids = set(old.keys()) - set(new.keys())
    for sid in deleted_ids:
        old[sid] = assoc(old[sid], "status", "DELETED")
    return merge(old, new).values()


@curry
def server_of_group(group_id, server):
    """
    Return True if server belongs to group_id. False otherwise
    """
    return group_id_from_metadata(server.get('metadata', {})) == group_id


@do
def get_scaling_group_servers(tenant_id, group_id, now,
                              all_as_servers=get_all_scaling_group_servers,
                              all_servers=get_all_server_details,
                              cache_class=CassScalingGroupServersCache):
    """
    Get a group's servers taken from cache if it exists. Updates cache
    if it is empty from newly fetched servers
    # NOTE: This function takes tenant_id even though the whole effect is
    # scoped on the tenant because cache calls require tenant_id. Should
    # they also not take tenant_id and work on the scope?

    :return: Servers as list of dicts
    :rtype: Effect
    """
    cache = cache_class(tenant_id, group_id)
    cached_servers, last_update = yield cache.get_servers(False)
    if last_update is None:
        servers = (yield all_as_servers()).get(group_id, [])
    else:
        current = yield all_servers()
        servers = mark_deleted_servers(cached_servers, current)
        servers = list(filter(server_of_group(group_id), servers))
    yield do_return(servers)


@do
def get_clb_contents():
    """Get Rackspace Cloud Load Balancer contents as list of `CLBNode`."""
    # If we get a CLBNotFoundError while fetching feeds, we should throw away
    # all nodes related to that load balancer, because we don't want to act on
    # data that we know is invalid/outdated (for example, if we can't fetch a
    # feed because CLB was deleted, we don't want to say that we have a node in
    # DRAINING with draining time of 0; we should just say that the node is
    # gone).

    def gone(r):
        return catch(CLBNotFoundError, lambda exc: r)
    lb_ids = [lb['id'] for lb in (yield _retry(get_clbs()))]
    node_reqs = [_retry(get_clb_nodes(lb_id).on(error=gone([])))
                 for lb_id in lb_ids]
    all_nodes = yield parallel(node_reqs)
    lb_nodes = {lb_id: [CLBNode.from_node_json(lb_id, node) for node in nodes]
                for lb_id, nodes in zip(lb_ids, all_nodes)}
    draining = [n for n in concat(lb_nodes.values())
                if n.description.condition == CLBNodeCondition.DRAINING]
    feeds = yield parallel(
        [_retry(get_clb_node_feed(n.description.lb_id, n.node_id).on(
            error=gone(None)))
         for n in draining]
    )
    nodes_to_feeds = dict(zip(draining, feeds))
    deleted_lbs = set([
        node.description.lb_id
        for (node, feed) in nodes_to_feeds.items() if feed is None])

    def update_drained_at(node):
        feed = nodes_to_feeds.get(node)
        if node.description.lb_id in deleted_lbs:
            return None
        if feed is not None:
            return assoc_obj(node, drained_at=extract_CLB_drained_at(feed))
        else:
            return node
    nodes = map(update_drained_at, concat(lb_nodes.values()))
    yield do_return(list(filter(bool, nodes)))


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
    eff = service_request(ServiceType.RACKCONNECT_V3, 'GET',
                          'load_balancer_pools')

    def on_listing_pools(lblist_result):
        _, body = lblist_result
        return parallel([
            service_request(ServiceType.RACKCONNECT_V3, 'GET',
                            append_segments('load_balancer_pools',
                                            lb_pool['id'], 'nodes')).on(
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
        tenant_id,
        group_id,
        now,
        get_scaling_group_servers=get_scaling_group_servers,
        get_clb_contents=get_clb_contents,
        get_rcv3_contents=get_rcv3_contents):
    """
    Gather all data relevant for convergence w.r.t given time,
    in parallel where possible.

    Returns an Effect of ([NovaServer], [LBNode]).
    """
    eff = parallel(
        [get_scaling_group_servers(tenant_id, group_id, now)
         .on(map(NovaServer.from_server_details_json)).on(list),
         get_clb_contents(),
         get_rcv3_contents()]
    ).on(lambda (servers, clb, rcv3): (servers, list(concat([clb, rcv3]))))
    return eff
