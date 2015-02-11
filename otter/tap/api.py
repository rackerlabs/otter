"""
Twisted Application plugin for otter API nodes.
"""

from functools import partial

import jsonfig

from silverberg.cluster import RoundRobinCassandraCluster
from silverberg.logger import LoggingCQLClient

from twisted.application.service import MultiService, Service
from twisted.application.strports import service
from twisted.internet import reactor
from twisted.internet.defer import gatherResults, maybeDeferred
from twisted.internet.endpoints import clientFromString
from twisted.internet.task import coiterate
from twisted.python import usage
from twisted.python.log import addObserver
from twisted.web.server import Site

from txkazoo import TxKazooClient

from otter.auth import generate_authenticator
from otter.bobby import BobbyClient
from otter.constants import get_service_configs
from otter.convergence.service import Converger, set_converger
from otter.effect_dispatcher import get_full_dispatcher
from otter.log import log
from otter.log.cloudfeeds import CloudFeedsObserver
from otter.models.cass import CassAdmin, CassScalingGroupCollection
from otter.rest.admin import OtterAdmin
from otter.rest.application import Otter
from otter.rest.bobby import set_bobby
from otter.scheduler import SchedulerService
from otter.supervisor import SupervisorService, set_supervisor
from otter.util.config import config_value, set_config_data
from otter.util.cqlbatch import TimingOutCQLClient
from otter.util.deferredutils import timeout_deferred


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
    A simple service that has functions to call when starting and stopping service
    """

    def __init__(self, start=None, stop=None):
        """
        :param start: A single argument callable to be called when service is started
        :param stop: A single argument callable to be called when service is stopped
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

    s = MultiService()

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

    store = CassScalingGroupCollection(cassandra_cluster, reactor)
    admin_store = CassAdmin(cassandra_cluster)

    bobby_url = config_value('bobby_url')
    if bobby_url is not None:
        set_bobby(BobbyClient(bobby_url))

    service_configs = get_service_configs(config)

    authenticator = generate_authenticator(reactor, config['identity'])
    dispatcher = get_full_dispatcher(reactor, authenticator, log,
                                     get_service_configs(config))
    supervisor = SupervisorService(authenticator, region, coiterate,
                                   service_configs)
    supervisor.setServiceParent(s)

    set_supervisor(supervisor)

    health_checker = HealthChecker(reactor, {
        'store': getattr(store, 'health_check', None),
        'kazoo': store.kazoo_health_check,
        'supervisor': supervisor.health_check
    })

    # Setup cassandra cluster to disconnect when otter shuts down
    if 'cassandra_cluster' in locals():
        s.addService(FunctionalService(stop=partial(call_after_supervisor,
                                                    cassandra_cluster.disconnect, supervisor)))

    otter = Otter(store, region, health_checker.health_check,
                  es_host=config_value('elasticsearch.host'))
    site = Site(otter.app.resource())
    site.displayTracebacks = False

    api_service = service(str(config_value('port')), site)
    api_service.setServiceParent(s)

    # Setup admin service
    admin_port = config_value('admin')
    if admin_port:
        admin = OtterAdmin(admin_store)
        admin_site = Site(admin.app.resource())
        admin_site.displayTracebacks = False
        admin_service = service(str(admin_port), admin_site)
        admin_service.setServiceParent(s)

    # setup cloud feed
    cf_conf = config.get('cloudfeeds', None)
    if cf_conf is not None:
        addObserver(
            CloudFeedsObserver(
                reactor=reactor, authenticator=authenticator,
                region=region, tenant_id=cf_conf['tenant_id'],
                service_configs=service_configs))

    # Setup Kazoo client
    if config_value('zookeeper'):
        threads = config_value('zookeeper.threads') or 10
        kz_client = TxKazooClient(hosts=config_value('zookeeper.hosts'),
                                  # Keep trying to connect until the end of time with
                                  # max interval of 10 minutes
                                  connection_retry=dict(max_tries=-1, max_delay=600),
                                  threads=threads, txlog=log.bind(system='kazoo'))
        # Don't timeout. Keep trying to connect forever
        d = kz_client.start(timeout=None)

        def on_client_ready(_):
            # Setup scheduler service after starting
            scheduler = setup_scheduler(s, store, kz_client)
            health_checker.checks['scheduler'] = scheduler.health_check
            otter.scheduler = scheduler
            # Set the client after starting
            # NOTE: There is small amount of time when the start is not finished
            # and the kz_client is not set in which case policy execution and group
            # delete will fail
            store.kz_client = kz_client
            # Setup kazoo to stop when shutting down
            s.addService(FunctionalService(
                stop=partial(call_after_supervisor,
                             kz_client.stop, supervisor)))

            # setup converger service
            converger_service = Converger(reactor, kz_client, dispatcher)
            s.addService(converger_service)
            set_converger(converger_service)

        d.addCallback(on_client_ready)
        d.addErrback(log.err, 'Could not start TxKazooClient')

    return s


def setup_scheduler(parent, store, kz_client):
    """
    Setup scheduler service
    """
    # Setup scheduler service
    if not config_value('scheduler') or config_value('mock'):
        return
    buckets = range(1, int(config_value('scheduler.buckets')) + 1)
    store.set_scheduler_buckets(buckets)
    partition_path = config_value('scheduler.partition.path') or '/scheduler_partition'
    time_boundary = config_value('scheduler.partition.time_boundary') or 15
    scheduler_service = SchedulerService(int(config_value('scheduler.batchsize')),
                                         int(config_value('scheduler.interval')),
                                         store, kz_client, partition_path, time_boundary,
                                         buckets)
    scheduler_service.setServiceParent(parent)
    return scheduler_service
