"""
Package for all otter specific logging functionality.
"""

from otter.log.setup import observer_factory
from otter.log.formatters import GELFFormat

__all__ = ['observer_factory', 'GELFFormat']
