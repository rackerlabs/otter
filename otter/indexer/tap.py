"""
The AtomHopper polling twisted plugin (to be started with twistd).
"""

import json

import hashlib

from twisted.internet import reactor

from twisted.web.client import Agent, HTTPConnectionPool

from twisted.python import usage
from twisted.python.reflect import namedAny
from twisted.application.service import MultiService

from otter.indexer.poller import FeedPollerService
from otter.indexer.state import FileStateStore


class Options(usage.Options):
    """Command line options for running the AtomHopper polling service
    """
    name = 'atomhopper-indexer'

    optParameters = [
        ["config", "C", None, "Config File"]
    ]


def makeService(config):
    """Make the FeedPollerService that will polling AtomHopper.
    """
    s = MultiService()

    config = json.loads(open(config['config']).read())

    agent = Agent(reactor, pool=HTTPConnectionPool(reactor, persistent=True))

    for service_name, service_desc in config['services'].iteritems():
        for url in service_desc['urls']:
            fps = FeedPollerService(
                agent,
                str(url),
                [namedAny(h)
                 for h in service_desc.get('event_handlers', [])],
                state_store=FileStateStore(hashlib.md5(url).hexdigest()))
            fps.setServiceParent(s)

    return s
