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

from otter.rest.application import root, set_store
from otter.models.cass import CassScalingGroupCollection

from silverberg.cluster import RoundRobinCassandraCluster


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
        self.update(jsonfig.from_path(self['config']))


def makeService(config):
    """
    Set up the otter-api service.
    """
    if not config.get('mock', False):
        seed_endpoints = [
            clientFromString(reactor, str(host))
            for host in config['cassandra']['seed_hosts']]

        cassandra_cluster = RoundRobinCassandraCluster(
            seed_endpoints,
            config['cassandra']['keyspace'])

        set_store(CassScalingGroupCollection(cassandra_cluster))

    s = MultiService()

    site = Site(root)
    site.displayTracebacks = False

    api_service = service(str(config['port']), site)
    api_service.setServiceParent(s)

    return s
