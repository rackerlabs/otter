"""
Observer factories which will be used to configure twistd logging.
"""
import sys
import socket

from otter.log.formatters import (
    JSONObserverWrapper,
    StreamObserverWrapper,
    SystemFilterWrapper,
    PEP3101FormattingWrapper,
    GELFObserverWrapper
)


def make_observer_chain(ultimate_observer, indent):
    """
    Return our feature observers wrapped our the ultimate_observer
    """
    return PEP3101FormattingWrapper(
        SystemFilterWrapper(
            GELFObserverWrapper(
                JSONObserverWrapper(
                    ultimate_observer,
                    sort_keys=True,
                    indent=indent),
                hostname=socket.gethostname())))


def observer_factory():
    """
    Log non-pretty JSON formatted GELF structures to sys.stdout.
    """
    return make_observer_chain(StreamObserverWrapper(sys.stdout), False)


def observer_factory_debug():
    """
    Log pretty JSON formatted GELF structures to sys.stdout.
    """
    return make_observer_chain(StreamObserverWrapper(sys.stdout), 2)

