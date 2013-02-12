"""
Package for all otter specific logging functionality.
"""

from otter.log.setup import observer_factory
from otter.log.formatters import GELFFormat

from twiggy import log
from twixxy.features.failure import failure

log = log.name('otter')
log.addFeature(failure)

__all__ = ['observer_factory', 'GELFFormat', 'log']
