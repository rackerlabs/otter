"""
Script to collect metrics (total desired, actual and pending) from a DC
"""

from __future__ import print_function

import json
import operator
import sys
import time
from collections import namedtuple
from datetime import datetime, timedelta
from functools import partial

import attr

from effect import Effect, Func, TypeDispatcher, ComposedDispatcher
from effect.do import do, do_return

from silverberg.client import ConsistencyLevel
from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import filter, get_in, groupby
from toolz.dicttoolz import keyfilter, merge
from toolz.functoolz import curry, identity
from toolz.itertoolz import mapcat

from twisted.application.internet import TimerService
from twisted.application.service import Service
from twisted.internet import defer, task
from twisted.internet.endpoints import clientFromString
from twisted.python import usage

from txeffect import deferred_performer, exc_info_to_failure, perform

from otter.auth import generate_authenticator
from otter.cloud_client import TenantScope, service_request
from otter.constants import ServiceType, get_service_configs
from otter.convergence.gathering import get_all_scaling_group_servers
from otter.effect_dispatcher import get_legacy_dispatcher, get_log_dispatcher
from otter.log import log as otter_log
from otter.log.intents import err
from otter.util.fileio import (
    ReadFileLines, WriteFileLines, get_dispatcher as file_dispatcher)
from otter.util.fp import partition_bool, predicate_all
from otter.util.timestamp import datetime_to_epoch


QUERY_GROUPS_OF_TENANTS = (
    'SELECT '
    '"tenantId", "groupId", desired, active, pending, created_at, status, '
    'deleting FROM scaling_group WHERE "tenantId" IN ({tids})')


def valid_group_row(row):
    return (
        row.get('created_at') is not None and
        row.get('desired') is not None and
        row.get('status') not in ('DISABLED', 'ERROR') and
        not row.get('deleting', False))


def get_specific_scaling_groups(client, tenant_ids):
    tids = ', '.join("'{}'".format(tid) for tid in tenant_ids)
    query = QUERY_GROUPS_OF_TENANTS.format(tids=tids)
    d = client.execute(query, {}, ConsistencyLevel.ONE)
    return d.addCallback(filter(valid_group_row))


def get_last_info(fname):
    eff = Effect(ReadFileLines(fname)).on(
        lambda lines: (int(lines[0]),
                       datetime.utcfromtimestamp(float(lines[1]))))

    def log_and_return(e):
        _eff = err(e, "error reading last tenant")
        return _eff.on(lambda _: (None, None))

    return eff.on(error=log_and_return)


def update_last_info(fname, tenants_len, time):
    eff = Effect(
        WriteFileLines(
            fname, [tenants_len, datetime_to_epoch(time)]))
    return eff.on(error=lambda e: err(e, "error updating last tenant"))


@attr.s
class GetAllGroups(object):
    pass


def get_todays_tenants(tenants, today, last_tenants_len, last_date):
    """
    Get tenants that are enabled till today
    """
    batch_size = 5
    tenants = sorted(tenants)
    if last_tenants_len is None:
        return tenants[:batch_size], batch_size, today
    days = (today - last_date).days
    if days <= 0:
        return tenants[:last_tenants_len], last_tenants_len, today
    if len(tenants) < last_tenants_len + batch_size:
        return tenants, len(tenants), today
    return (tenants[:last_tenants_len + batch_size],
            last_tenants_len + batch_size, today)


@do
def get_todays_scaling_groups(convergence_tids, fname):
    """
    Get scaling groups that from tenants that are enabled till today
    """
    groups = yield Effect(GetAllGroups())
    non_conv_tenants = set(groups.keys()) - set(convergence_tids)
    last_tenants_len, last_date = yield get_last_info(fname)
    now = yield Effect(Func(datetime.utcnow))
    tenants, last_tenants_len, last_date = get_todays_tenants(
        non_conv_tenants, now, last_tenants_len, last_date)
    yield update_last_info(fname, last_tenants_len, last_date)
    yield do_return(
        keyfilter(lambda t: t in set(tenants + convergence_tids), groups))


def get_scaling_groups(client):
    """
    Get valid scaling groups grouped on tenantId from Cassandra

    :param :class:`silverber.client.CQLClient` client: A cassandra client
    :return: `Deferred` fired with ``dict`` of the form
        {"tenantId1": [{group_dict_1...}, {group_dict_2..}],
         "tenantId2": [{group_dict_1...}, {group_dict_2..}, ...]}
    """
    d = get_scaling_group_rows(
        client, props=["status", "deleting", "created_at"])
    d.addCallback(filter(valid_group_row))
    return d.addCallback(groupby(lambda g: g["tenantId"]))


@defer.inlineCallbacks
def get_scaling_group_rows(client, props=None, batch_size=100):
    """
    Return scaling group rows from Cassandra as a list of ``dict`` where each
    dict has 'tenantId', 'groupId', 'desired', 'active', 'pending'
    and any other properties given in `props`

    :param :class:`silverber.client.CQLClient` client: A cassandra client
    :param ``list`` props: List of extra properties to extract
    :param int batch_size: Number of groups to fetch at a time
    :return: `Deferred` fired with ``list`` of ``dict``
    """
    # TODO: Currently returning all groups as one giant list for now.
    # Will try to use Twisted tubes to do streaming later
    _props = set(['"tenantId"', '"groupId"', 'desired',
                  'active', 'pending']) | set(props or [])
    query = ('SELECT ' + ','.join(sorted(list(_props))) +
             ' FROM scaling_group {where} LIMIT :limit;')
    where_key = 'WHERE "tenantId"=:tenantId AND "groupId">:groupId'
    where_token = 'WHERE token("tenantId") > token(:tenantId)'

    # We first start by getting all groups limited on batch size
    # It will return groups sorted first based on hash of tenant id
    # and then based group id. Note that only tenant id is sorted
    # based on hash; group id is sorted normally
    batch = yield client.execute(query.format(where=''),
                                 {'limit': batch_size}, ConsistencyLevel.ONE)
    if len(batch) < batch_size:
        defer.returnValue(batch)

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
    defer.returnValue(groups)


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


def get_all_metrics_effects(tenanted_groups, log, _print=False):
    """
    Gather server data for and produce metrics for all groups
    across all tenants in a region

    :param dict tenanted_groups: Scaling groups grouped with tenantId
    :param bool _print: Should the function print while processing?

    :return: ``list`` of :obj:`Effect` of (``list`` of :obj:`GroupMetrics`)
             or None
    """
    effs = []
    for tenant_id, groups in tenanted_groups.iteritems():
        eff = get_all_scaling_group_servers(
            server_predicate=lambda s: s['status'] in ('ACTIVE', 'BUILD'))
        eff = Effect(TenantScope(eff, tenant_id))
        eff = eff.on(partial(get_tenant_metrics, tenant_id, groups,
                             _print=_print))
        eff = eff.on(
            error=lambda exc_info: log.err(exc_info_to_failure(exc_info)))
        effs.append(eff)
    return effs


def _perform_limited_effects(dispatcher, effects, limit):
    """
    Perform the effects in parallel up to a limit.

    It'd be nice if effect.parallel had a "limit" parameter.
    """
    # TODO: Use cooperator instead
    sem = defer.DeferredSemaphore(limit)
    defs = [sem.run(perform, dispatcher, eff) for eff in effects]
    return defer.gatherResults(defs)


def get_all_metrics(dispatcher, tenanted_groups, log, _print=False,
                    get_all_metrics_effects=get_all_metrics_effects):
    """
    Gather server data and produce metrics for all groups across all tenants
    in a region.

    :param dispatcher: An Effect dispatcher.
    :param dict tenanted_groups: Scaling Groups grouped on tenantid
    :param bool _print: Should the function print while processing?

    :return: ``list`` of `GroupMetrics` as `Deferred`
    """
    effs = get_all_metrics_effects(tenanted_groups, log, _print=_print)
    d = _perform_limited_effects(dispatcher, effs, 10)
    d.addCallback(filter(lambda x: x is not None))
    return d.addCallback(lambda x: reduce(operator.add, x, []))


@do
def add_to_cloud_metrics(ttl, region, total_desired, total_actual,
                         total_pending, no_tenants, no_groups, log=None):
    """
    Add total number of desired, actual and pending servers of a region
    to Cloud metrics.

    :param dict conf: Metrics configuration, will contain tenant ID of tenant
        used to ingest metrics and other conf like ttl
    :param str region: which region's metric is collected
    :param int total_desired: Total number of servers currently desired
        in the region
    :param int total_actual: Total number of servers currently
        there in the region
    :param int total_pending: Total number of servers currently
        building in a region
    :param int no_tenants: total number of tenants
    :param int no_tenants: total number of groups

    :return: `Effect` with None
    """
    epoch = yield Effect(Func(time.time))
    metric_part = {'collectionTime': int(epoch * 1000),
                   'ttlInSeconds': ttl}
    totals = [('desired', total_desired), ('actual', total_actual),
              ('pending', total_pending), ('tenants', no_tenants),
              ('groups', no_groups)]
    data = [merge(metric_part,
                  {'metricValue': value,
                   'metricName': '{}.{}'.format(region, metric)})
            for metric, value in totals]
    yield service_request(ServiceType.CLOUD_METRICS_INGEST,
                          'POST', 'ingest', data=data, log=log)

def connect_cass_servers(reactor, config):
    """
    Connect to Cassandra servers and return the connection
    """
    seed_endpoints = [clientFromString(reactor, str(host))
                      for host in config['seed_hosts']]
    return RoundRobinCassandraCluster(
        seed_endpoints, config['keyspace'], disconnect_on_cancel=True)


def get_dispatcher(reactor, authenticator, log, service_configs, client):
    return ComposedDispatcher([
        get_legacy_dispatcher(reactor, authenticator, log, service_configs),
        get_log_dispatcher(log, {}),
        TypeDispatcher({
            GetAllGroups: deferred_performer(
                lambda d, i: get_scaling_groups(client))
        }),
        file_dispatcher()
    ])


@defer.inlineCallbacks
def collect_metrics(reactor, config, log, client=None, authenticator=None,
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

    :return: :class:`Deferred` fired with ``list`` of `GroupMetrics`
    """
    convergence_tids = config.get('convergence-tenants', [])
    _client = client or connect_cass_servers(reactor, config['cassandra'])
    authenticator = authenticator or generate_authenticator(reactor,
                                                            config['identity'])
    dispatcher = get_dispatcher(reactor, authenticator, log,
                                get_service_configs(config), _client)

    # calculate metrics
    tenanted_groups = yield perform(
        dispatcher,
        get_todays_scaling_groups(convergence_tids, "last_tenant.txt"))
    group_metrics = yield get_all_metrics(
        dispatcher, tenanted_groups, log, _print=_print)

    # Calculate total desired, actual and pending
    total_desired, total_actual, total_pending = 0, 0, 0
    for group_metric in group_metrics:
        total_desired += group_metric.desired
        total_actual += group_metric.actual
        total_pending += group_metric.pending
    log.msg(
        'total desired: {td}, total_actual: {ta}, total pending: {tp}',
        td=total_desired, ta=total_actual, tp=total_pending)
    if _print:
        print('total desired: {}, total actual: {}, total pending: {}'.format(
            total_desired, total_actual, total_pending))

    # Add to cloud metrics
    metr_conf = config.get("metrics", None)
    if metr_conf is not None:
        eff = add_to_cloud_metrics(
            metr_conf['ttl'], config['region'], total_desired,
            total_actual, total_pending, log)
        eff = Effect(TenantScope(eff, metr_conf['tenant_id']))
        yield perform(dispatcher, eff)
        log.msg('added to cloud metrics')
        if _print:
            print('added to cloud metrics')
    if _print:
        group_metrics.sort(key=lambda g: abs(g.desired - g.actual),
                           reverse=True)
        print('groups sorted as per divergence', *group_metrics, sep='\n')

    # Disconnect only if we created the client
    if not client:
        yield _client.disconnect()

    defer.returnValue(group_metrics)


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


def metrics_set(metrics):
    return set((g.tenant_id, g.group_id) for g in metrics)


def unchanged_divergent_groups(clock, current, timeout, group_metrics):
    """
    Return list of GroupMetrics that have been divergent and unchanged for
    timeout seconds

    :param IReactorTime clock: Twisted time used to track
    :param dict current: Currently tracked divergent groups
    :param float timeout: Timeout in seconds
    :param list group_metrics: List of group metrics

    :return: (updated current, List of (group, divergent_time) tuples)
    """
    converged, diverged = partition_bool(
        lambda gm: gm.actual + gm.pending == gm.desired, group_metrics)
    # stop tracking all converged and deleted groups
    deleted = set(current.keys()) - metrics_set(group_metrics)
    updated = current.copy()
    for g in metrics_set(converged) | deleted:
        updated.pop(g, None)
    # Start tracking divergent groups depending on whether they've changed
    now = clock.seconds()
    to_log, new = [], {}
    for gm in diverged:
        pair = (gm.tenant_id, gm.group_id)
        if pair in updated:
            last_time, values = updated[pair]
            if values != hash((gm.desired, gm.actual, gm.pending)):
                del updated[pair]
                continue
            time_diff = now - last_time
            if time_diff > timeout and time_diff % timeout <= 60:
                # log on intervals of timeout. For example, if timeout is 1 hr
                # then log every hour it remains diverged
                to_log.append((gm, time_diff))
        else:
            new[pair] = now, hash((gm.desired, gm.actual, gm.pending))
    return merge(updated, new), to_log


class MetricsService(Service, object):
    """
    Service collects metrics on continuous basis
    """

    def __init__(self, reactor, config, log, clock=None, collect=None):
        """
        Initialize the service by connecting to Cassandra and setting up
        authenticator

        :param reactor: Twisted reactor for connection purposes
        :param dict config: All the config necessary to run the service.
            Comes from config file
        :param IReactorTime clock: Optional reactor for timer purpose
        """
        self._client = connect_cass_servers(reactor, config['cassandra'])
        self.log = log
        self.reactor = reactor
        self._divergent_groups = {}
        self.divergent_timeout = get_in(
            ['metrics', 'divergent_timeout'], config, 3600)
        self._service = TimerService(
            get_in(['metrics', 'interval'], config, default=60),
            collect or self.collect,
            reactor,
            config,
            self.log,
            client=self._client,
            authenticator=generate_authenticator(reactor, config['identity']))
        self._service.clock = clock or reactor

    @defer.inlineCallbacks
    def collect(self, *a, **k):
        try:
            metrics = yield collect_metrics(*a, **k)
            self._divergent_groups, to_log = unchanged_divergent_groups(
                self.reactor, self._divergent_groups, self.divergent_timeout,
                metrics)
            for group, duration in to_log:
                self.log.err(
                    ValueError(""),  # Need to give an exception to log err
                    ("Group {group_id} of {tenant_id} remains diverged "
                     "and unchanged for {divergent_time}"),
                    tenant_id=group.tenant_id, group_id=group.group_id,
                    desired=group.desired, actual=group.actual,
                    pending=group.pending,
                    divergent_time=str(timedelta(seconds=duration)))
        except Exception:
            self.log.err(None, "Error collecting metrics")

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


metrics_log = otter_log.bind(system='otter.metrics')


def makeService(config):
    """
    Set up the otter-metrics service.
    """
    from twisted.internet import reactor
    return MetricsService(reactor, dict(config), metrics_log)


if __name__ == '__main__':
    config = json.load(open(sys.argv[1]))
    # TODO: Take _print as cmd-line arg and pass it.
    task.react(collect_metrics, (config, metrics_log, None, None, True))
