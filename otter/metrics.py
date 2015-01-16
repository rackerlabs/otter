"""
Script to collect metrics (total desired, actual and pending) from a DC
"""

from __future__ import print_function

import json
import operator
import sys
import time
from collections import namedtuple
from functools import partial

from effect.twisted import exc_info_to_failure, perform

from silverberg.client import ConsistencyLevel
from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import filter, get_in, groupby
from toolz.dicttoolz import merge
from toolz.functoolz import identity

from twisted.application.internet import TimerService
from twisted.application.service import Service
from twisted.internet import defer, task
from twisted.internet.endpoints import clientFromString
from twisted.python import usage

from otter.auth import generate_authenticator
from otter.constants import ServiceType, get_service_mapping
from otter.convergence.gathering import get_scaling_group_servers
from otter.effect_dispatcher import get_dispatcher
from otter.http import get_request_func
from otter.log import log as otter_log
from otter.util.fp import predicate_all


# TODO: Remove this and pass it from service to other functions
metrics_log = otter_log.bind(system='otter.metrics')


@defer.inlineCallbacks
def get_scaling_groups(client, props=None, batch_size=100, group_pred=None):
    """
    Return scaling groups from Cassandra as a list of ``dict`` where each
    dict has 'tenantId', 'groupId', 'desired', 'active', 'pending'
    and any other properties given in `props`

    :param :class:`silverber.client.CQLClient` client: A cassandra client
    :param ``list`` props: List of extra properties to extract
    :oaram int batch_size: Number of groups to fetch at a time
    :return: `Deferred` with ``list`` of ``dict``
    """
    # TODO: Currently returning all groups as one giant list for now.
    # Will try to use Twisted tubes to do streaming later
    _props = set(['"tenantId"', '"groupId"', 'desired',
                  'active', 'pending', 'created_at']) | set(props or [])
    query = ('SELECT ' + ','.join(sorted(list(_props))) +
             ' FROM scaling_group {where} LIMIT :limit;')
    where_key = 'WHERE "tenantId"=:tenantId AND "groupId">:groupId'
    where_token = 'WHERE token("tenantId") > token(:tenantId)'

    # setup function that removes groups not having desired
    has_desired = lambda g: g['desired'] is not None
    has_created_at = lambda g: g['created_at'] is not None
    group_pred = group_pred or identity
    group_filter = filter(predicate_all(has_desired,
                                        has_created_at,
                                        group_pred))

    # We first start by getting all groups limited on batch size
    # It will return groups sorted first based on hash of tenant id
    # and then based group id. Note that only tenant id is sorted
    # based on hash; group id is sorted normally
    batch = yield client.execute(query.format(where=''),
                                 {'limit': batch_size}, ConsistencyLevel.ONE)
    if len(batch) < batch_size:
        defer.returnValue(group_filter(batch))

    # We got batch size response. That means there are probably more groups
    groups = batch
    while batch != []:
        # We start by getting all the groups of last tenant ID we received
        # except the ones we already got. We do that by asking
        # groups > last group id since groups are sorted
        tenant_id = batch[-1]['tenantId']
        while len(batch) == batch_size:
            batch = yield client.execute(query.format(where=where_key),
                                         {'limit': batch_size,
                                          'tenantId': tenant_id,
                                          'groupId': batch[-1]['groupId']},
                                         ConsistencyLevel.ONE)
            groups.extend(batch)
        # We then get next tenant's groups by using there hash value. i.e
        # tenants whose hash > last tenant id we just fetched
        batch = yield client.execute(query.format(where=where_token),
                                     {'limit': batch_size,
                                      'tenantId': tenant_id},
                                     ConsistencyLevel.ONE)
        groups.extend(batch)
    defer.returnValue(group_filter(groups))


GroupMetrics = namedtuple('GroupMetrics',
                          'tenant_id group_id desired actual pending')


def get_tenant_metrics(tenant_id, scaling_groups, servers, _print=False):
    """
    Produce per-group metrics for all the groups of a tenant

    :param list scaling_groups: Tenant's scaling groups as dict from CASS
    :param dict servers: Servers from Nova grouped based on scaling group ID.
                         Expects only ACTIVE or BUILD servers
    :return: ``list`` of (tenantId, groupId, desired, actual) GroupMetrics
    """
    if _print:
        print('processing tenant {} with groups {} and servers {}'.format(
              tenant_id, len(scaling_groups), len(servers)))
    metrics = []
    for group in scaling_groups:
        group_id = group['groupId']
        create_metrics = partial(GroupMetrics, tenant_id,
                                 group_id, group['desired'])
        if group_id not in servers:
            metrics.append(create_metrics(0, 0))
        else:
            active = len(list(filter(lambda s: s['status'] == 'ACTIVE',
                                     servers[group_id])))
            metrics.append(
                create_metrics(active, len(servers[group_id]) - active))
    return metrics


def get_all_metrics_effects(cass_groups, get_request_func_for_tenant,
                            log, _print=False):
    """
    Gather server data for and produce metrics for all groups
    across all tenants in a region

    :param iterable cass_groups: Groups as retrieved from cassandra
    :param get_request_func_for_tenant: Function of tenant_id -> request
    :param bool _print: Should the function print while processing?

    :return: ``list`` of :obj:`Effect` of (``list`` of :obj:`GroupMetrics`)
             or None
    """
    tenanted_groups = groupby(lambda g: g['tenantId'], cass_groups)
    effs = []
    for tenant_id, groups in tenanted_groups.iteritems():
        request_func = get_request_func_for_tenant(tenant_id)
        eff = get_scaling_group_servers(
            request_func,
            server_predicate=lambda s: s['status'] in ('ACTIVE', 'BUILD'))
        eff = eff.on(partial(get_tenant_metrics, tenant_id,
                             groups, _print=_print))
        eff = eff.on(
            error=lambda exc_info: log.err(exc_info_to_failure(exc_info)))
        effs.append(eff)
    return effs


def _perform_limited_effects(effects, clock, limit):
    """
    Perform the effects in parallel up to a limit.

    It'd be nice if effect.parallel had a "limit" parameter.
    """
    # TODO: Use cooperator instead
    dispatcher = get_dispatcher(clock)
    sem = defer.DeferredSemaphore(limit)
    defs = [sem.run(perform, dispatcher, eff) for eff in effects]
    return defer.gatherResults(defs)


def get_all_metrics(cass_groups, authenticator, service_mapping, region,
                    clock=None, _print=False):
    """
    Gather server data and produce metrics for all groups across all tenants
    in a region.

    :param iterable cass_groups: Groups as retrieved from cassandra
    :param :obj:`otter.auth.IAuthenticator` authenticator:
        object that impersonates a tenant
    :param str services: service mapping from config
    :param str region: DC region
    :param bool _print: Should the function print while processing?

    :return: ``list`` of `GroupMetrics` as `Deferred`
    """
    def req_func_for_tenant(tenant_id):
        return get_request_func(authenticator, tenant_id, metrics_log,
                                service_mapping, region)
    effs = get_all_metrics_effects(
        cass_groups, req_func_for_tenant, metrics_log, _print=_print)
    d = _perform_limited_effects(effs, clock, 10)
    d.addCallback(filter(lambda x: x is not None))
    return d.addCallback(lambda x: reduce(operator.add, x, []))


def add_to_cloud_metrics(request_func, conf, region, total_desired,
                         total_actual, total_pending, log=None):
    """
    Add total number of desired, actual and pending servers of a region
    to Cloud metrics

    :param dict conf: Metrics configuration, will contain tenant ID of tenant
                      used to ingest metrics and other conf like ttl
    :param str region: which region's metric is collected
    :param int total_desired: Total number of servers currently desired
                              in the region
    :param int total_actual: Total number of servers currently
                             there in the region
    :param int total_pending: Total number of servers currently
                              building in a region

    :return: `Deferred` with None
    """
    metric_part = {'collectionTime': int(time.time() * 1000),
                   'ttlInSeconds': conf['ttl']}
    totals = [('desired', total_desired), ('actual', total_actual),
              ('pending', total_pending)]
    return request_func(ServiceType.CLOUD_METRICS_INGEST, 'POST', 'ingest',
                        data=[merge(metric_part,
                                    {'metricValue': value,
                                     'metricName': '{}.{}'.format(region,
                                                                  metric)})
                              for metric, value in totals],
                        log=log)


def connect_cass_servers(reactor, config):
    """
    Connect to Cassandra servers and return the connection
    """
    seed_endpoints = [clientFromString(reactor, str(host))
                      for host in config['seed_hosts']]
    return RoundRobinCassandraCluster(
        seed_endpoints, config['keyspace'], disconnect_on_cancel=True)


@defer.inlineCallbacks
def collect_metrics(reactor, config, client=None, authenticator=None,
                    _print=False):
    """
    Start collecting the metrics

    :param reactor: Twisted reactor
    :param dict config: Configuration got from file containing all info
                        needed to collect metrics
    :param :class:`silverberg.client.CQLClient` client:
            Optional cassandra client. A new client will be created
            if this is not given and disconnected before returing
    :param :class:`otter.auth.IAuthenticator` authenticator:
            Optional authenticator. A new authenticator will be created
            if this is not given
    :param bool _print: Should debug messages be printed to stdout?

    :return: :class:`Deferred` with None
    """
    _client = client or connect_cass_servers(reactor, config['cassandra'])
    authenticator = authenticator or generate_authenticator(reactor,
                                                            config['identity'])
    service_mapping = get_service_mapping(config)

    # calculate metrics
    cass_groups = yield get_scaling_groups(
        _client, props=['status'],
        group_pred=lambda g: g['status'] != 'DISABLED')
    group_metrics = yield get_all_metrics(
        cass_groups, authenticator, service_mapping, config['region'],
        clock=reactor, _print=_print)

    # Calculate total desired, actual and pending
    total_desired, total_actual, total_pending = 0, 0, 0
    for group_metric in group_metrics:
        total_desired += group_metric.desired
        total_actual += group_metric.actual
        total_pending += group_metric.pending
    metrics_log.msg(
        'total desired: {td}, total_actual: {ta}, total pending: {tp}',
        td=total_desired, ta=total_actual, tp=total_pending)
    if _print:
        print('total desired: {}, total actual: {}, total pending: {}'.format(
            total_desired, total_actual, total_pending))

    # Add to cloud metrics
    req_func = get_request_func(
        authenticator, config['metrics']['tenant_id'], metrics_log,
        service_mapping, config['metrics']['region'])
    eff = add_to_cloud_metrics(
        req_func, config['metrics'], config['region'], total_desired,
        total_actual, total_pending, log=metrics_log)
    yield perform(get_dispatcher(reactor), eff)
    metrics_log.msg('added to cloud metrics')
    if _print:
        print('added to cloud metrics')
        group_metrics.sort(key=lambda g: abs(g.desired - g.actual),
                           reverse=True)
        print('groups sorted as per divergence', *group_metrics, sep='\n')

    # Diconnect only if we created the client
    if not client:
        yield _client.disconnect()


class Options(usage.Options):
    """
    Options for otter-metrics service
    """

    optParameters = [["config", "c", "config.json",
                      "path to JSON configuration file"]]

    def postOptions(self):
        """
        Parse config file and add nova service name
        """
        self.open = getattr(self, 'open', None) or open  # For testing
        self.update(json.load(self.open(self['config'])))


class MetricsService(Service, object):
    """
    Service collects metrics on continuous basis
    """

    def __init__(self, reactor, config, log, clock=None):
        """
        Initialize the service by connecting to Cassandra and setting up
        authenticator

        :param reactor: Twisted reactor
        :param dict config: All the config necessary to run the service.
                            Comes from config file
        :param IReactorTime clock: Optional reactor for testing timer
        """
        self._client = connect_cass_servers(reactor, config['cassandra'])
        collect = lambda *a, **k: collect_metrics(*a, **k).addErrback(log.err)
        self._service = TimerService(
            get_in(['metrics', 'interval'], config, default=60), collect,
            reactor, config, client=self._client,
            authenticator=generate_authenticator(reactor, config['identity']))
        self._service.clock = clock or reactor

    def startService(self):
        """
        Start this service by starting internal TimerService
        """
        Service.startService(self)
        return self._service.startService()

    def stopService(self):
        """
        Stop service by stopping the timerservice and disconnecting cass client
        """
        Service.stopService(self)
        d = self._service.stopService()
        return d.addCallback(lambda _: self._client.disconnect())


def makeService(config):
    """
    Set up the otter-metrics service.
    """
    from twisted.internet import reactor
    return MetricsService(reactor, dict(config), metrics_log)


if __name__ == '__main__':
    config = json.load(open(sys.argv[1]))
    # TODO: Take _print as cmd-line arg and pass it.
    task.react(collect_metrics, (config, None, None, True))
