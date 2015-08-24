"""
Observer factories which will be used to configure twistd logging.
"""
import socket
import sys

from otter.log.formatters import (
    ErrorFormattingWrapper,
    FanoutObserver,
    JSONObserverWrapper,
    ObserverWrapper,
    PEP3101FormattingWrapper,
    StreamObserverWrapper,
    SystemFilterWrapper,
    set_fanout,
    throttling_wrapper,
)
from otter.log.spec import SpecificationObserverWrapper


def make_observer_chain(ultimate_observer, indent):
    """
    Return our feature observers wrapped our the ultimate_observer
    """
    fanout = FanoutObserver(
        ObserverWrapper(
            JSONObserverWrapper(
                ultimate_observer,
                sort_keys=True,
                indent=indent or None),
            hostname=socket.gethostname()))
    set_fanout(fanout)

    return throttling_wrapper(
        SpecificationObserverWrapper(
            PEP3101FormattingWrapper(
                SystemFilterWrapper(
                    ErrorFormattingWrapper(
                        fanout)))))


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
