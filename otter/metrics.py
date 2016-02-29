"""
Script to collect metrics (total desired, actual and pending) from a DC
"""

from __future__ import print_function

import json
import operator
import sys
import time
from collections import defaultdict, namedtuple
from datetime import timedelta
from functools import partial

import attr

from effect import ComposedDispatcher, Effect, Func
from effect.do import do

from silverberg.cluster import RoundRobinCassandraCluster

from toolz.curried import filter, get_in
from toolz.dicttoolz import keyfilter, merge
from toolz.functoolz import compose, flip

from twisted.application.internet import TimerService
from twisted.application.service import Service
from twisted.internet import defer, task
from twisted.internet.endpoints import clientFromString
from twisted.python import usage

from txeffect import exc_info_to_failure, perform

from otter.auth import generate_authenticator
from otter.cloud_client import TenantScope, service_request
from otter.constants import ServiceType, get_service_configs
from otter.convergence.composition import tenant_is_enabled
from otter.convergence.gathering import get_all_scaling_group_servers
from otter.convergence.model import (
    NovaServer, ServerState, group_id_from_metadata)
from otter.effect_dispatcher import get_legacy_dispatcher, get_log_dispatcher
from otter.log import log as otter_log
from otter.models.cass import CassScalingGroupCollection
from otter.models.intents import GetAllGroups, get_model_dispatcher
from otter.util.config import config_value
from otter.util.fp import partition_bool


GroupMetrics = namedtuple('GroupMetrics',
                          'tenant_id group_id desired actual pending')


def get_tenant_metrics(tenant_id, scaling_groups, grouped_servers,
                       _print=False):
    """
    Produce per-group metrics for all the groups of a tenant

    :param list scaling_groups: Tenant's scaling groups as dict from CASS
    :param dict grouped_servers: Servers from Nova grouped based on
        scaling group ID.
    :return: generator of (tenantId, groupId, desired, actual) GroupMetrics
    """
    if _print:
        print('processing tenant {} with groups {} and servers {}'.format(
              tenant_id, len(scaling_groups), len(grouped_servers)))

    groups = {g['groupId']: g for g in scaling_groups}

    for group_id in set(groups.keys() + grouped_servers.keys()):
        servers = grouped_servers.get(group_id, [])
        if group_id in groups:
            group = groups[group_id]
        else:
            group = {'groupId': group_id_from_metadata(servers[0]['metadata']),
                     'desired': 0}
        servers = map(NovaServer.from_server_details_json, servers)
        _len = compose(len, list, flip(filter, servers))
        active = _len(lambda s: s.state == ServerState.ACTIVE)
        bad = _len(lambda s: s.state in (ServerState.SHUTOFF,
                                         ServerState.ERROR,
                                         ServerState.DELETED))
        yield GroupMetrics(tenant_id, group['groupId'], group['desired'],
                           active, len(servers) - bad - active)


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
        eff = get_all_scaling_group_servers()
        eff = Effect(TenantScope(eff, tenant_id))
        eff = eff.on(partial(get_tenant_metrics, tenant_id, groups,
                             _print=_print))
        eff = eff.on(list)
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


@attr.s
class Metric(object):
    desired = attr.ib(default=0)
    actual = attr.ib(default=0)
    pending = attr.ib(default=0)


def calc_total(group_metrics):
    """
    Calculate total metric for all groups and per tenant

    :param group_metrics: List of :obj:`GroupMetric`
    :return (``dict``, :obj:`Metric`) where dict is tenant-id -> `Metric`
        representing per tenant metric and second element is total metric
    """
    tenanted = defaultdict(Metric)
    total = Metric()
    for gm in group_metrics:
        total.desired += gm.desired
        total.actual += gm.actual
        total.pending += gm.pending
        tenanted[gm.tenant_id].desired += gm.desired
        tenanted[gm.tenant_id].actual += gm.actual
        tenanted[gm.tenant_id].pending += gm.pending
    return tenanted, total


@do
def add_to_cloud_metrics(ttl, region, group_metrics, no_tenants, config,
                         log=None, _print=False):
    """
    Add total number of desired, actual and pending servers of a region
    to Cloud metrics.

    :param str region: which region's metric is collected
    :param group_metrics: List of :obj:`GroupMetric`
    :param int no_tenants: total number of tenants
    :param dict config: Config json dict containing convergence tenants info
    :param log: Optional logger
    :param bool _print: Should it print activity on stdout? Useful when running
        as a script

    :return: `Effect` with None
    """
    epoch = yield Effect(Func(time.time))
    metric_part = {'collectionTime': int(epoch * 1000),
                   'ttlInSeconds': ttl}

    tenanted_metrics, total = calc_total(group_metrics)
    if log is not None:
        log.msg(
            'total desired: {td}, total_actual: {ta}, total pending: {tp}',
            td=total.desired, ta=total.actual, tp=total.pending)
    if _print:
        print('total desired: {}, total actual: {}, total pending: {}'.format(
            total.desired, total.actual, total.pending))

    metrics = [('desired', total.desired), ('actual', total.actual),
               ('pending', total.pending), ('tenants', no_tenants),
               ('groups', len(group_metrics))]
    for tenant_id, metric in sorted(tenanted_metrics.items()):
        metrics.append(("{}.desired".format(tenant_id), metric.desired))
        metrics.append(("{}.actual".format(tenant_id), metric.actual))
        metrics.append(("{}.pending".format(tenant_id), metric.pending))

    # convergence tenants desired and actual
    conv_tenants = keyfilter(
        partial(tenant_is_enabled,
                get_config_value=lambda k: get_in([k], config)),
        tenanted_metrics)
    conv_desired = sum(m.desired for m in conv_tenants.itervalues())
    conv_actual = sum(m.actual for m in conv_tenants.itervalues())
    metrics.extend(
        [("conv_desired", conv_desired), ("conv_actual", conv_actual),
         ("conv_divergence", conv_desired - conv_actual)])

    data = [merge(metric_part,
                  {'metricValue': value,
                   'metricName': '{}.{}'.format(region, metric)})
            for metric, value in metrics]
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


def get_dispatcher(reactor, authenticator, log, service_configs, store):
    return ComposedDispatcher([
        get_legacy_dispatcher(reactor, authenticator, log, service_configs),
        get_log_dispatcher(log, {}),
        get_model_dispatcher(log, store)
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
    _client = client or connect_cass_servers(reactor, config['cassandra'])
    authenticator = authenticator or generate_authenticator(reactor,
                                                            config['identity'])
    store = CassScalingGroupCollection(_client, reactor, 1000)
    dispatcher = get_dispatcher(reactor, authenticator, log,
                                get_service_configs(config), store)

    # calculate metrics
    tenanted_groups = yield perform(dispatcher, Effect(GetAllGroups()))
    group_metrics = yield get_all_metrics(
        dispatcher, tenanted_groups, log, _print=_print)

    # Add to cloud metrics
    metr_conf = config.get("metrics", None)
    if metr_conf is not None:
        eff = add_to_cloud_metrics(
            metr_conf['ttl'], config['region'], group_metrics,
            len(tenanted_groups), config, log, _print)
        eff = Effect(TenantScope(eff, metr_conf['tenant_id']))
        yield perform(dispatcher, eff)
        log.msg('added to cloud metrics')
        if _print:
            print('added to cloud metrics')
    if _print:
        group_metrics.sort(key=lambda g: abs(g.desired - g.actual),
                           reverse=True)
        print('groups sorted as per divergence')
        print('\n'.join(map(str, group_metrics)))

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
