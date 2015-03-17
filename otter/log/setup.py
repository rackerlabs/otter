"""
Observer factories which will be used to configure twistd logging.
"""
import socket
import sys

from otter.log.formatters import (
    ErrorFormattingWrapper,
    JSONObserverWrapper,
    ObserverWrapper,
    PEP3101FormattingWrapper,
    StreamObserverWrapper,
    SystemFilterWrapper,
    throttling_wrapper,
)


def make_observer_chain(ultimate_observer, indent):
    """
    Return our feature observers wrapped our the ultimate_observer
    """
    return throttling_wrapper(
        PEP3101FormattingWrapper(
            SystemFilterWrapper(
                ErrorFormattingWrapper(
                    ObserverWrapper(
                        JSONObserverWrapper(
                            ultimate_observer,
                            sort_keys=True,
                            indent=indent or None),
                        hostname=socket.gethostname())))))


def observer_factory():
    """
    Log non-pretty JSON formatted structures to sys.stdout.
    """
    return make_observer_chain(StreamObserverWrapper(sys.stdout), False)


def observer_factory_debug():
    """
    Log pretty JSON formatted structures to sys.stdout.
    """
    return make_observer_chain(StreamObserverWrapper(sys.stdout), 2)
