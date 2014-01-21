"""
Twisted Application plugin for otter API nodes.
"""
import jsonfig

from twisted.python import usage

from twisted.internet import reactor
from twisted.internet.defer import DeferredList, maybeDeferred, succeed
from twisted.internet.task import coiterate

from twisted.internet.endpoints import clientFromString

from twisted.application.strports import service
from twisted.application.service import MultiService

from twisted.web.server import Site

from txkazoo import TxKazooClient

from otter.rest.admin import OtterAdmin
from otter.rest.application import Otter
from otter.rest.bobby import set_bobby
from otter.util.config import set_config_data, config_value
from otter.models.cass import CassAdmin, CassScalingGroupCollection
from otter.models.mock import MockAdmin, MockScalingGroupCollection
from otter.scheduler import SchedulerService

from otter.supervisor import SupervisorService, set_supervisor
from otter.auth import ImpersonatingAuthenticator
from otter.auth import RetryingAuthenticator
from otter.auth import CachingAuthenticator

from otter.log import log
from silverberg.cluster import RoundRobinCassandraCluster
from silverberg.logger import LoggingCQLClient
from otter.bobby import BobbyClient


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

    optFlags = [
        ["mock", "m", "whether to use a mock back end instead of cassandra"]
    ]

    def postOptions(self):
        """
        Merge our commandline arguments with our config file.
        """
        # Inject some default values into the config.  Right now this is
        # only used to support distinguishing between staging and production.
        self.update({
            'regionOverrides': {},
            'cloudServersOpenStack': 'cloudServersOpenStack',
            'cloudLoadBalancers': 'cloudLoadBalancers'
        })

        self.update(jsonfig.from_path(self['config']))

        # The staging service catalog has some unfortunate differences
        # from the production one, so these are here to hint at the
        # correct ocnfiguration for staging.
        if self.get('environment') == 'staging':
            self['cloudServersOpenStack'] = 'cloudServersPreprod'
            self['regionOverrides']['cloudLoadBalancers'] = 'STAGING'


class HealthChecker(object):
    """
    A object to store other objects with ``.health_check`` attributes, that has
    a single health check function that calls all the others and assembles their
    results.

    ``.health_check`` should return a tuple of ``(bool, dict)``, the boolean
    being whether the object is healthy, and the dictionary being extra data
    to be included.

    :param healthed: a dictionary containing objects that have `.health_check`
        attributes to be called, mapped to the key the health check data should
        live under.
    """
    def __init__(self, healthed=None):
        self.healthed = healthed
        if not healthed:
            self.healthed = {}

    def health_check(self):
        """
        Synthesizes all health checks and returns a JSON blob containing the
        key ``healthy``, which is whether all the healthed items are healthy,
        and one key and value per healthed item.
        """
        # splitting off keys and values here because we want the keys
        # correlated with the results of the DeferredList at the end
        # (if self.healthed changes in the interim,  the DeferredList may not
        # match up with self.healthed.keys() later)
        keys, checks = ([], [])
        for k, v in self.healthed.iteritems():
            keys.append(k)
            healthcheck = getattr(v, 'health_check', None)
            if healthcheck:
                checks.append(maybeDeferred(healthcheck).addErrback(
                    lambda _: (False, {'reason': 'error during health check'})))
            else:
                checks.append(succeed(
                    (False, {'reason': 'invalid health check object'})))

        d = DeferredList(checks)

        def assembleResults(results):
            # because DeferredList returns with (bool, results)
            results = [r[1] for r in results]
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
    set_config_data(dict(config))

    if not config_value('mock'):
        seed_endpoints = [
            clientFromString(reactor, str(host))
            for host in config_value('cassandra.seed_hosts')]

        cassandra_cluster = LoggingCQLClient(RoundRobinCassandraCluster(
            seed_endpoints,
            config_value('cassandra.keyspace')), log.bind(system='otter.silverberg'))

        store = CassScalingGroupCollection(cassandra_cluster)
        admin_store = CassAdmin(cassandra_cluster)
    else:
        store = MockScalingGroupCollection()
        admin_store = MockAdmin()

    bobby_url = config_value('bobby_url')
    if bobby_url is not None:
        set_bobby(BobbyClient(bobby_url))

    cache_ttl = config_value('identity.cache_ttl')

    if cache_ttl is None:
        # FIXME: Pick an arbitrary cache ttl value based on absolutely no
        # science.
        cache_ttl = 300

    authenticator = CachingAuthenticator(
        reactor,
        RetryingAuthenticator(
            reactor,
            ImpersonatingAuthenticator(
                config_value('identity.username'),
                config_value('identity.password'),
                config_value('identity.url'),
                config_value('identity.admin_url')),
            max_retries=config_value('identity.max_retries'),
            retry_interval=config_value('identity.retry_interval')),
        cache_ttl)

    s = MultiService()

    supervisor = SupervisorService(authenticator.authenticate_tenant, coiterate)
    supervisor.setServiceParent(s)

    set_supervisor(supervisor)

    otter = Otter(store)
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

    # Setup Kazoo client
    if config_value('zookeeper'):
        threads = config_value('zookeeper.threads') or 10
        kz_client = TxKazooClient(hosts=config_value('zookeeper.hosts'),
                                  threads=threads, txlog=log.bind(system='kazoo'))
        d = kz_client.start()
        # Setup scheduler service after starting
        d.addCallback(lambda _: setup_scheduler(s, store, kz_client))
        # Set the client after starting
        # NOTE: There is small amount of time when the start is not finished
        # and the kz_client is not set in which case policy execution and group
        # delete will fail
        d.addCallback(lambda _: setattr(store, 'kz_client', kz_client))
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
