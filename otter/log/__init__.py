"""
Package for all otter specific logging functionality.
"""

from otter.log.setup import observer_factory, observer_factory_debug
from otter.log.bound import BoundLog, DEBUG
from twisted.python.log import msg, err

log = BoundLog(msg, err).bind(system='otter')

__all__ = ['observer_factory', 'observer_factory_debug', 'log', 'DEBUG']
