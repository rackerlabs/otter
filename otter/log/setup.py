"""
Set up twiggy for the project
"""
import sys

from twisted.python import log
from otter.log.formatters import GELFFormat

stdout = sys.stdout


def writeLog(msg):
    stdout.write(msg)
    stdout.write('\n')
    stdout.flush()


def observer_factory():
    """
    Setup twiggy and return a twisted log observer.
    """
    return GELFFormat(writeLog, 'otter')


def observer_factory_debug():
    """
    Setup twiggy and return a twisted log observer.
    """
    return log.FileLogObserver(sys.stdout).emit
