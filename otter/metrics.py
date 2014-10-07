"""
Script to collect metrics (total desired, actual and pending) from a DC
"""

from __future__ import print_function

from functools import partial
import sys
import json
from collections import namedtuple
import time

from twisted.internet import task, defer
from twisted.internet.endpoints import clientFromString
from twisted.application.internet import TimerService
from twisted.python import usage

from silverberg.client import ConsistencyLevel
from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import groupby, filter, get_in
from toolz.dicttoolz import merge

from otter.auth import (
    RetryingAuthenticator, ImpersonatingAuthenticator, authenticate_user,
    extract_token)

# TODO: Below function has knowledge of service catalog and is independent of
# worker code. This and other similar code in worker should be moved to otter.auth
from otter.worker.launch_server_v1 import public_endpoint_url

from otter.convergence import get_scaling_group_servers
from otter.util.http import append_segments, headers, check_success
from otter.log import log as otter_log


@defer.inlineCallbacks
def get_scaling_groups(client, props=None, batch_size=100):
    """
    Return scaling groups from Cassandra as a list of ``dict`` where each dict has
    'tenantId', 'groupId', 'desired', 'active', 'pending' and any other properties
    given in `props`

    :param :class:`silverber.client.CQLClient` client: A cassandra client oject
    :param ``list`` props: List of extra properties to extract
    :oaram int batch_size: Number of groups to fetch at a time
    :return: `Deferred` with ``list`` of ``dict``
    """
    # TODO: Currently returning all groups as one giant list for now. Will try to use Twisted tubes
    # to do streaming later
    _props = set(['"tenantId"', '"groupId"', 'desired',
                  'active', 'pending', 'created_at']) | set(props or [])
    query = ('SELECT ' + ','.join(sorted(list(_props))) +
             ' FROM scaling_group {where} LIMIT :limit;')
    where_key = 'WHERE "tenantId"=:tenantId AND "groupId">:groupId'
    where_token = 'WHERE token("tenantId") > token(:tenantId)'

    # setup function that removes groups not having desired
    group_filter = filter(lambda g: g['desired'] is not None and g['created_at'] is not None)

    # We first start by getting all groups limited on batch size
    # It will return groups sorted first based on hash of tenant id and then based
    # group id. Note that only tenant id is sorted based on hash; group id is sorted
    # normally
    batch = yield client.execute(query.format(where=''),
                                 {'limit': batch_size}, ConsistencyLevel.ONE)
    if len(batch) < batch_size:
        defer.returnValue(group_filter(batch))

    # We got batch size response. That means there are probably more groups
    groups = batch
    while batch != []:
        # We start by getting all the groups of last tenant ID we received except
        # the ones we already got. We do that by asking groups > last group id since
        # groups are sorted
        tenantId = batch[-1]['tenantId']
        while len(batch) == batch_size:
            batch = yield client.execute(query.format(where=where_key),
                                         {'limit': batch_size, 'tenantId': tenantId,
                                          'groupId': batch[-1]['groupId']},
                                         ConsistencyLevel.ONE)
            groups.extend(batch)
        # We then get next tenant's groups by using there hash value. i.e
        # tenants whose hash > last tenant id we just fetched
        batch = yield client.execute(query.format(where=where_token),
                                     {'limit': batch_size, 'tenantId': tenantId},
                                     ConsistencyLevel.ONE)
        groups.extend(batch)
    defer.returnValue(group_filter(groups))


@defer.inlineCallbacks
def check_rackconnect(client):
    """
    Rackconnect metrics
    """
    groups = yield get_scaling_groups(client, props=['launch_config'])
    for group in groups:
        lbpool = get_in(['args', 'server', 'metadata', 'RackConnectLBPool'],
                        json.loads(group['launch_config']))
        if lbpool is not None:
            print('Tenant: {} Group: {} RackconnectLBPool: {}'.format(
                  group['tenantId'], group['groupId'], lbpool))


def check_tenant_config(tenant_id, groups, grouped_servers):
    """
    Check if servers in the tenant's groups are different, i.e. have different flavor
    or image
    """
    props = (['flavor', 'id'], ['image', 'id'])
    for group in groups:
        group_id = group['groupId']
        if group_id not in grouped_servers:
            continue
        uniques = set(map(lambda s: tuple(get_in(p, s) for p in props),
                          grouped_servers[group_id]))
        if len(uniques) > 1:
            print('tenant {} group {} diff types: {}'.format(tenant_id, group_id, uniques))


@defer.inlineCallbacks
def check_diff_configs(client, authenticator, nova_service, region, clock=None):
    """
    Find groups having servers with different launch config in them
    """
    cass_groups = yield get_scaling_groups(client)
    tenanted_groups = groupby(lambda g: g['tenantId'], cass_groups)
    print('got tenants', len(tenanted_groups))

    defs = []
    sem = defer.DeferredSemaphore(10)
    for tenant_id, groups in tenanted_groups.iteritems():
        d = sem.run(
            get_scaling_group_servers, tenant_id, authenticator,
            nova_service, region, sfilter=lambda s: s['status'] in ('ACTIVE', 'BUILD'),
            clock=clock)
        d.addCallback(partial(check_tenant_config, tenant_id, groups))
        defs.append(d)

    yield defer.gatherResults(defs)


GroupMetrics = namedtuple('GroupMetrics', 'tenant_id group_id desired actual pending')


def get_tenant_metrics(tenant_id, scaling_groups, servers, _print=False):
    """
    Get tenant's metrics

    :param ``list`` of ``dict`` scaling_groups: Tenant's scaling groups from CASS
    :param ``dict`` servers: Servers from Nova grouped based on scaling group ID
    :return: ``list`` of (tenantId, groupId, desired, actual) GroupMetrics namedtuples
    """
    if _print:
        print('processing tenant {} with groups {} and servers {}'.format(
              tenant_id, len(scaling_groups), len(servers)))
    metrics = []
    for group in scaling_groups:
        group_id = group['groupId']
        create_metrics = partial(GroupMetrics, tenant_id, group_id, group['desired'])
        if group_id not in servers:
            metrics.append(create_metrics(0, 0))
        else:
            active = len(list(filter(lambda s: s['status'] == 'ACTIVE', servers[group_id])))
            metrics.append(create_metrics(active, len(servers[group_id]) - active))
    return metrics


def get_all_metrics(cass_groups, authenticator, nova_service, region,
                    clock=None, _print=False):
    """
    Get all group's metrics

    :param iterable cass_groups: Groups got from cassandra as
    :param :class:`otter.auth.IAuthenticator` authenticator: object that impersonates a tenant
    :param str nova_service: Nova service name in service catalog
    :param str region: DC region
    :param :class:`twisted.internet.IReactorTime` clock: IReactorTime provider
    :param bool _print: Should the function print while processing?

    :return: ``list`` of `GroupMetrics` as `Deferred`
    """
    # TODO: Use cooperator instead
    sem = defer.DeferredSemaphore(10)
    tenanted_groups = groupby(lambda g: g['tenantId'], cass_groups)
    defs = []
    group_metrics = []
    for tenant_id, groups in tenanted_groups.iteritems():
        d = sem.run(
            get_scaling_group_servers, tenant_id, authenticator,
            nova_service, region, sfilter=lambda s: s['status'] in ('ACTIVE', 'BUILD'),
            clock=clock)
        d.addCallback(partial(get_tenant_metrics, tenant_id, groups, _print=_print))
        d.addCallback(group_metrics.extend)
        defs.append(d)

    return defer.gatherResults(defs).addCallback(lambda _: group_metrics)


@defer.inlineCallbacks
def add_to_cloud_metrics(conf, identity_url, region, total_desired, total_actual,
                         total_pending, _treq=None):
    """
    Add total number of desired, actual and pending servers of a region to Cloud metrics

    :param ``dict`` conf: Metrics configuration, will contain credentials used to authenticate
                        to cloud metrics, and other conf like ttl
    :param str identity_url: URL of identity API to authenticate users given in `conf`
    :param str region: which region's metric is collected
    :param int total_desired: Total number of servers currently desired in a region
    :param int total_actual: Total number of servers currently there in a region
    :param int total_pending: Total number of servers currently building in a region
    :param ``treq`` _treq: Optional treq implementation for testing

    :return: `Deferred` with None
    """
    # TODO: Have generic authentication function that auths, gets the service URL
    # and returns the token
    resp = yield authenticate_user(identity_url, conf['username'], conf['password'],
                                   log=otter_log)
    token = extract_token(resp)

    if _treq is None:  # pragma: no cover
        import treq
        _treq = treq

    url = public_endpoint_url(resp['access']['serviceCatalog'], conf['service'], conf['region'])

    metric_part = {'collectionTime': int(time.time() * 1000),
                   'ttlInSeconds': conf['ttl']}
    totals = [('desired', total_desired), ('actual', total_actual), ('pending', total_pending)]
    d = _treq.post(
        append_segments(url, 'ingest'), headers=headers(token),
        data=json.dumps([merge(metric_part,
                               {'metricValue': value,
                                'metricName': '{}.{}'.format(region, metric)})
                         for metric, value in totals]))
    d.addCallback(check_success, [200], _treq=_treq)
    d.addCallback(_treq.content)
    yield d


def get_authenticator(reactor, identity):
    """
    Return authenticator based on identity config
    """
    return RetryingAuthenticator(
        reactor,
        ImpersonatingAuthenticator(
            identity['username'],
            identity['password'],
            identity['url'],
            identity['admin_url']))


def connect_cass_servers(reactor, config):
    """
    Connect to Cassandra servers and return the connection
    """
    seed_endpoints = [clientFromString(reactor, str(host)) for host in config['seed_hosts']]
    return RoundRobinCassandraCluster(seed_endpoints, config['keyspace'], disconnect_on_cancel=True)


@defer.inlineCallbacks
def main(reactor, config, _print=False):
    """
    Start collecting the metrics
    """
    client = connect_cass_servers(reactor, config['cassandra'])
    authenticator = get_authenticator(reactor, config['identity'])

    cass_groups = yield get_scaling_groups(client)
    group_metrics = yield get_all_metrics(
        cass_groups, authenticator, config['services']['nova'], config['region'],
        clock=reactor, _print=_print)

    total_desired, total_actual, total_pending = reduce(
        lambda (td, ta, tp), g: (td + g.desired, ta + g.actual, tp + g.pending),
        group_metrics, (0, 0, 0))
    if _print:
        print('total desired: {}, total actual: {}, total pending: {}'.format(
            total_desired, total_actual, total_pending))
    yield add_to_cloud_metrics(config['metrics'], config['identity']['url'],
                               config['region'], total_desired, total_actual,
                               total_pending)
    if _print:
        print('added to cloud metrics')
        group_metrics.sort(key=lambda g: abs(g.desired - g.actual), reverse=True)
        print('groups sorted as per divergence', *group_metrics, sep='\n')

    yield client.disconnect()


class Options(usage.Options):
    """
    Options for otter-metrics service
    """

    optParameters = [["config", "c", "config.json", "path to JSON configuration file"]]

    def postOptions(self):
        """
        Parse config file and add nova service name
        """
        self.open = getattr(self, 'open', None) or open  # For testing
        self.update(json.load(self.open(self['config'])))
        self.update({'services': {'nova': 'cloudServersOpenStack'}})


def makeService(config):
    """
    Set up the otter-metrics service.
    """
    from twisted.internet import reactor
    config = dict(config)
    return TimerService(
        get_in(['metrics', 'interval'], config, default=60), main, reactor, config)


if __name__ == '__main__':
    config = json.load(open(sys.argv[2]))
    config['services'] = {'nova': 'cloudServersOpenStack'}
    # TODO: Take _print as cmd-line arg and pass it.
    task.react(main, (config, True))
