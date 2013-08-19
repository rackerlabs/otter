"""
Twisted Application plugin for otter API nodes.
"""
import jsonfig

from twisted.python import usage

from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString

from twisted.application.strports import service
from twisted.application.service import MultiService

from twisted.web.server import Site

from otter.rest.application import root, set_store, set_bobby
from otter.util.config import set_config_data, config_value
from otter.models.cass import CassScalingGroupCollection
from otter.scheduler import SchedulerService

from otter.supervisor import Supervisor, set_supervisor
from otter.auth import ImpersonatingAuthenticator
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

        set_store(CassScalingGroupCollection(cassandra_cluster))

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
        ImpersonatingAuthenticator(
            config_value('identity.username'),
            config_value('identity.password'),
            config_value('identity.url'),
            config_value('identity.admin_url')),
        cache_ttl)

    supervisor = Supervisor(authenticator.authenticate_tenant)

    set_supervisor(supervisor)

    s = MultiService()

    site = Site(root)
    site.displayTracebacks = False

    api_service = service(str(config_value('port')), site)
    api_service.setServiceParent(s)

    if config_value('scheduler') and not config_value('mock'):
        scheduler_service = SchedulerService(int(config_value('scheduler.batchsize')),
                                             int(config_value('scheduler.interval')),
                                             cassandra_cluster)
        scheduler_service.setServiceParent(s)

    return s
