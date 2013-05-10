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
    fanout
)

from otter.log.graylog import GELFObserverWrapper
from otter.log.graylog import GraylogUDPPublisher


def observer_factory():
    """
    Log pretty JSON formatted GELF structures to sys.stdout.
    """
    return PEP3101FormattingWrapper(
        SystemFilterWrapper(
            GELFObserverWrapper(
                JSONObserverWrapper(
                    fanout(StreamObserverWrapper(sys.stdout),
                           GraylogUDPPublisher()),
                    sort_keys=True,
                    indent=2),
                hostname=socket.gethostname())))

observer_factory_debug = observer_factory
