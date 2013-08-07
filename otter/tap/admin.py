"""
Twisted Application plugin for the otter admin API.
"""
import jsonfig
import warnings

from twisted.python import usage

from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString

from twisted.application.strports import service
from twisted.application.service import MultiService

from twisted.web.server import Site
from twisted.python import log

try:
    from txairbrake.observers import AirbrakeLogObserver as _a
    AirbrakeLogObserver = _a   # to get around pyflakes
except ImportError:
    AirbrakeLogObserver = None

try:
    from otter.log.graylog import GraylogUDPPublisher as _g
    GraylogUDPPublisher = _g   # to get around pyflakes
except ImportError:
    GraylogUDPPublisher = None

from otter.rest.application import admin_app, set_store
from otter.util.config import set_config_data, config_value
from otter.log.setup import make_observer_chain
from otter.models.cass import CassScalingGroupCollection

from otter.supervisor import Supervisor, set_supervisor
from otter.auth import ImpersonatingAuthenticator
from otter.auth import CachingAuthenticator

from silverberg.cluster import RoundRobinCassandraCluster


class Options(usage.Options):
    """
    Options for the otter-admin-api node.
    """

    optParameters = [
        ["port", "p", "tcp:9001",
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

        self.update(jsonfig.from_path(self['config']))


def makeService(config):
    """
    Set up the otter-admin-api service.
    """
    set_config_data(dict(config))

    # Try to configure graylog and airbrake.

    if config_value('graylog'):
        if GraylogUDPPublisher is not None:
            log.addObserver(
                make_observer_chain(
                    GraylogUDPPublisher(**config_value('graylog')), False))
        else:
            warnings.warn("There is a configuration option for Graylog, but "
                          "txgraylog is not installed.")

    if config_value('airbrake'):
        if AirbrakeLogObserver is not None:
            airbrake = AirbrakeLogObserver(
                config_value('airbrake.api_key'),
                config_value('environment'),
                use_ssl=True
            )

            airbrake.start()
        else:
            warnings.warn("There is a configuration option for Airbrake, but "
                          "txairbrake is not installed.")

    if not config_value('mock'):
        seed_endpoints = [
            clientFromString(reactor, str(host))
            for host in config_value('cassandra.seed_hosts')]

        cassandra_cluster = RoundRobinCassandraCluster(
            seed_endpoints,
            config_value('cassandra.keyspace'))

        set_store(CassScalingGroupCollection(cassandra_cluster))

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

    site = Site(admin_app.resource())
    site.displayTracebacks = False

    api_service = service(str(config_value('port')), site)
    api_service.setServiceParent(s)

    return s
