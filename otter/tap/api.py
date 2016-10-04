"""
Twisted Application plugin for otter API nodes.
"""
import os

from copy import deepcopy
from functools import partial

import jsonfig

from kazoo.client import KazooClient

from silverberg.cluster import RoundRobinCassandraCluster
from silverberg.logger import LoggingCQLClient

from toolz.dicttoolz import get_in

from twisted.application.internet import TimerService
from twisted.application.service import MultiService, Service
from twisted.application.strports import service
from twisted.internet import reactor
from twisted.internet.defer import gatherResults, maybeDeferred
from twisted.internet.endpoints import clientFromString
from twisted.internet.task import coiterate
from twisted.python import usage
from twisted.python.threadpool import ThreadPool
from twisted.web.server import Site

from txkazoo import TxKazooClient
from txkazoo.log import TxLogger
from txkazoo.recipe.watchers import watch_children

from otter.auth import generate_authenticator
from otter.bobby import BobbyClient
from otter.constants import (
    CONVERGENCE_DIRTY_DIR,
    CONVERGENCE_PARTITIONER_PATH,
    get_service_configs)
from otter.convergence.selfheal import SelfHeal
from otter.convergence.service import Converger
from otter.effect_dispatcher import get_full_dispatcher
from otter.log import log
from otter.log.cloudfeeds import CloudFeedsObserver
from otter.log.formatters import add_to_fanout
from otter.models.cass import CassAdmin, CassScalingGroupCollection
from otter.rest.admin import OtterAdmin
from otter.rest.application import Otter
from otter.rest.bobby import set_bobby
from otter.scheduler import SchedulerService
from otter.supervisor import SupervisorService, set_supervisor
from otter.util import zk
from otter.util.config import config_value, set_config_data
from otter.util.cqlbatch import TimingOutCQLClient
from otter.util.deferredutils import timeout_deferred
from otter.util.zkpartitioner import Partitioner

assert os.environ.get("PYRSISTENT_NO_C_EXTENSION"), (
    "The environment variable PYRSISTENT_NO_C_EXTENSION must be set to "
    "a non-empty string because the C extension sometimes causes segfaults "
    "in otter.")


class Options(usage.Options):
    """
    Options for the otter-api node.

    TODO: Force some common parameters in a base class.
    TODO: Tracing support.
    TODO: Debugging.
    TODO: Environments.
    TODO: Admin HTTP interface.
    TODO: Specify store
    """

    optParameters = [
        ["port", "p", "tcp:9000",
         "strports description of the port for API connections."],
        ["config", "c", "config.json",
         "path to JSON configuration file."]
    ]

    def postOptions(self):
        """
        Merge our commandline arguments with our config file.
        """
        self.update(jsonfig.from_path(self['config']))


class FunctionalService(Service, object):
    """
    A simple service that has functions to call when starting and
    stopping service.
    """

    def __init__(self, start=None, stop=None):
        """
        :param start: A single argument callable to be called when service
            is started
        :param stop: A single argument callable to be called when service
            is stopped
        """
        self._start = start
        self._stop = stop

    def startService(self):
        """
        Start the service by calling stored function
        """
        Service.startService(self)
        if self._start:
            return self._start()

    def stopService(self):
        """
        Stop the service by calling stored function
        """
        Service.stopService(self)
        if self._stop:
            return self._stop()


def call_after_supervisor(func, supervisor):
    """
    Call function after supervisor jobs have completed

    Returns Deferred that fires with return value of `func`
    """
    d = supervisor.deferred_pool.notify_when_empty()
    d.addCallback(lambda _: func())
    return d


class HealthChecker(object):
    """
    A dictionary to store callables that are health checks, that has a single
    health check function that calls all the others and assembles their
    results.

    The health check callabls should return a tuple of ``(bool, dict)``, the
    boolean being whether the object is healthy, and the dictionary being extra
    data to be included.

    :param checks: a dictionary containing the name of things to health check
        mapped to their health check callabls
    """
    def __init__(self, clock, checks=None):
        self.clock = clock
        self.checks = checks
        if checks is None:
            self.checks = {}

    def health_check(self):
        """
        Synthesizes all health checks and returns a JSON blob containing the
        key ``healthy``, which is whether all the health checks are healthy,
        and one key and value per health check.
        """
        # splitting off keys and values here because we want the keys
        # correlated with the results of the DeferredList at the end
        # (if self.checks changes in the interim, the DeferredList may not
        # match up with self.checks.keys() later)
        keys, checks = ([], [])
        for k, v in self.checks.iteritems():
            keys.append(k)
            d = maybeDeferred(v)
            timeout_deferred(d, 15, self.clock, '{} health check'.format(k))
            d.addErrback(
                lambda f: (False, {'reason': f.getTraceback()}))
            checks.append(d)

        d = gatherResults(checks)

        def assembleResults(results):
            results = [{'healthy': r[0], 'details': r[1]} for r in results]
            healthy = all(r['healthy'] for r in results)

            summary = dict(zip(keys, results))
            summary['healthy'] = healthy
            return summary

        return d.addCallback(assembleResults)


def makeService(config):
    """
    Set up the otter-api service.
    """
    config = dict(config)
    set_config_data(config)

    parent = MultiService()

    region = config_value('region')

    seed_endpoints = [
        clientFromString(reactor, str(host))
        for host in config_value('cassandra.seed_hosts')]

    cassandra_cluster = LoggingCQLClient(
        TimingOutCQLClient(
            reactor,
            RoundRobinCassandraCluster(
                seed_endpoints,
                config_value('cassandra.keyspace'),
                disconnect_on_cancel=True),
            config_value('cassandra.timeout') or 30),
        log.bind(system='otter.silverberg'))

    store = CassScalingGroupCollection(
        cassandra_cluster, reactor, config_value('limits.absolute.maxGroups'))
    admin_store = CassAdmin(cassandra_cluster)

    bobby_url = config_value('bobby_url')
    if bobby_url is not None:
        set_bobby(BobbyClient(bobby_url))

    service_configs = get_service_configs(config)

    authenticator = generate_authenticator(reactor, config['identity'])
    supervisor = SupervisorService(authenticator, region, coiterate,
                                   service_configs)
    supervisor.setServiceParent(parent)

    set_supervisor(supervisor)

    health_checker = HealthChecker(reactor, {
        'store': getattr(store, 'health_check', None),
        'kazoo': store.kazoo_health_check,
        'supervisor': supervisor.health_check
    })

    # Setup cassandra cluster to disconnect when otter shuts down
    if 'cassandra_cluster' in locals():
        parent.addService(FunctionalService(stop=partial(
            call_after_supervisor, cassandra_cluster.disconnect, supervisor)))

    otter = Otter(store, region, health_checker.health_check)
    site = Site(otter.app.resource())
    site.displayTracebacks = False

    api_service = service(str(config_value('port')), site)
    api_service.setServiceParent(parent)

    # Setup admin service
    admin_port = config_value('admin')
    if admin_port:
        admin = OtterAdmin(admin_store)
        admin_site = Site(admin.app.resource())
        admin_site.displayTracebacks = False
        admin_service = service(str(admin_port), admin_site)
        admin_service.setServiceParent(parent)

    # setup cloud feed
    cf_conf = config.get('cloudfeeds', None)
    if cf_conf is not None:
        id_conf = deepcopy(config['identity'])
        id_conf['strategy'] = 'single_tenant'
        add_to_fanout(CloudFeedsObserver(
            reactor=reactor,
            authenticator=generate_authenticator(reactor, id_conf),
            tenant_id=cf_conf['tenant_id'],
            region=region,
            service_configs=service_configs))

    # Setup Kazoo client
    if config_value('zookeeper'):
        threads = config_value('zookeeper.threads') or 10
        disable_logs = config_value('zookeeper.no_logs')
        threadpool = ThreadPool(maxthreads=threads)
        sync_kz_client = KazooClient(
            hosts=config_value('zookeeper.hosts'),
            # Keep trying to connect until the end of time with
            # max interval of 10 minutes
            connection_retry=dict(max_tries=-1, max_delay=600),
            logger=None if disable_logs else TxLogger(log.bind(system='kazoo'))
        )
        kz_client = TxKazooClient(reactor, threadpool, sync_kz_client)
        # Don't timeout. Keep trying to connect forever
        d = kz_client.start(timeout=None)

        def on_client_ready(_):
            dispatcher = get_full_dispatcher(reactor, authenticator, log,
                                             get_service_configs(config),
                                             kz_client, store, supervisor,
                                             cassandra_cluster)

            # Setup scheduler service after starting
            scheduler = setup_scheduler(parent, dispatcher, store, kz_client)
            if scheduler is not None:
                health_checker.checks['scheduler'] = scheduler.health_check
                otter.scheduler = scheduler

            # Give dispatcher to Otter REST object
            otter.dispatcher = dispatcher

            # Set the client and dispatcher after starting
            # NOTE: There is small amount of time when the start is
            # not finished and the kz_client is not set in which case
            # policy execution and group delete will fail
            store.kz_client = kz_client
            store.dispatcher = dispatcher

            # Setup kazoo to stop when shutting down
            parent.addService(FunctionalService(
                stop=partial(call_after_supervisor,
                             kz_client.stop, supervisor)))

            setup_converger(
                parent, kz_client, dispatcher,
                config_value('converger.interval') or 10,
                config_value('converger.build_timeout') or 3600,
                config_value('converger.limited_retry_iterations') or 10,
                config_value('converger.step_limits') or {})

            # Setup selfheal service
            sh_svc = setup_selfheal_service(
                reactor, config, dispatcher, health_checker, log)
            if sh_svc is not None:
                parent.addService(sh_svc)

        d.addCallback(on_client_ready)
        d.addErrback(log.err, 'Could not start TxKazooClient')

    return parent


def setup_selfheal_service(clock, config, dispatcher, health_checker, log):
    """
    Setup selfheal timer service and return it.

    :param clock: :obj:`IReactorTime` provider
    :param dict config: Configuration dict containing selfheal info
    :param dispatcher: Effect dispatcher
    :param health_checker: ``HealthChecker`` object where SelfHeal's health
        check will be added
    :param log: :obj:`BoundLog` logger used by service

    :return: selfheal service or None if relevant config is not found
    :rtype: :obj:`IService`
    """
    if "selfheal" not in config:
        return None
    interval = get_in(["selfheal", "interval"], config, no_default=True)
    selfheal = SelfHeal(clock, dispatcher, config_value, interval, log)
    func, lock = zk.locked_logged_func(
        dispatcher, "/selfheallock", log, "selfheal-lock-acquired", selfheal)
    health_checker.checks["selfheal"] = zk.create_health_check(lock)
    sh_timer = TimerService(interval, func)
    sh_timer.clock = clock
    return sh_timer


def setup_converger(parent, kz_client, dispatcher, interval, build_timeout,
                    limited_retry_iterations, step_limits):
    """
    Create a Converger service, which has a Partitioner as a child service, so
    that if the Converger is stopped, the partitioner is also stopped.
    """
    partitioner_factory = partial(
        Partitioner,
        kz_client=kz_client,
        interval=interval,
        partitioner_path=CONVERGENCE_PARTITIONER_PATH,
        time_boundary=15,  # time boundary
    )
    cvg = Converger(log, dispatcher, 10, partitioner_factory, build_timeout,
                    interval / 2, limited_retry_iterations, step_limits)
    cvg.setServiceParent(parent)
    watch_children(kz_client, CONVERGENCE_DIRTY_DIR, cvg.divergent_changed)


def setup_scheduler(parent, dispatcher, store, kz_client):
    """
    Setup scheduler service based on the configuration and return service
    object. If "scheduler" config is not found then return `None`.
    """
    # Setup scheduler service
    if not config_value('scheduler') or config_value('mock'):
        return None
    buckets = range(1, int(config_value('scheduler.buckets')) + 1)
    store.set_scheduler_buckets(buckets)
    partition_path = (config_value('scheduler.partition.path') or
                      '/scheduler_partition')
    time_boundary = config_value('scheduler.partition.time_boundary') or 15
    partitioner_factory = partial(
        Partitioner,
        kz_client, int(config_value('scheduler.interval')), partition_path,
        buckets, time_boundary)
    scheduler_service = SchedulerService(
        dispatcher, int(config_value('scheduler.batchsize')),
        store, partitioner_factory)
    scheduler_service.setServiceParent(parent)
    return scheduler_service
