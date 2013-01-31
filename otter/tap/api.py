"""
Twisted Application plugin for otter API nodes.
"""

from twisted.python import usage

from twisted.application.strports import service
from twisted.application.service import MultiService

from twisted.web.server import Site

from otter.rest.application import root


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
    ]


def makeService(config):
    """
    Set up the otter-api service.
    """
    s = MultiService()

    site = Site(root)
    site.displayTracebacks = False

    api_service = service(config['port'], site)
    api_service.setServiceParent(s)

    return s
