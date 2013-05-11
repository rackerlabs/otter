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
)

from otter.log.graylog import GELFObserverWrapper


def make_observer_chain(ultimate_observer):
    """
    Return our feature observers wrapped our the ultimate_observer
    """
    return PEP3101FormattingWrapper(
        SystemFilterWrapper(
            GELFObserverWrapper(
                JSONObserverWrapper(
                    ultimate_observer,
                    sort_keys=True,
                    indent=2),
                hostname=socket.gethostname())))


def observer_factory():
    """
    Log pretty JSON formatted GELF structures to sys.stdout.
    """
    return make_observer_chain(StreamObserverWrapper(sys.stdout))

observer_factory_debug = observer_factory
