"""
Observer factories which will be used to configure twistd logging.
"""
import sys
import socket

from otter.log.formatters import (
    GELFObserverWrapper,
    JSONObserverWrapper,
    StreamObserverWrapper
)


def observer_factory():
    """
    Log JSON formatted GELF structures to sys.stdout.
    """
    return GELFObserverWrapper(
        JSONObserverWrapper(
            StreamObserverWrapper(sys.stdout)),
        hostname=socket.gethostname())


def observer_factory_debug():
    """
    Log pretty JSON formatted GELF structures to sys.stdout.
    """
    return GELFObserverWrapper(
        JSONObserverWrapper(
            StreamObserverWrapper(sys.stdout),
            sort_keys=True,
            indent=2),
        hostname=socket.gethostname())
