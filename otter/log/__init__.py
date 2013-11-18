"""
Package for all otter specific logging functionality.
"""

from otter.log.setup import observer_factory, observer_factory_debug
from otter.log.bound import BoundLog
from twisted.python.log import msg, err

log = BoundLog(msg, err).bind(system='otter')

def audit(log):
    """
    Single method to ensure that the log object is an audit log (by binding
    the audit log param)

    :param log: a bound log object
    :returns: a bound log object with keyword that specifies it as an audit
        log already bound
    """
    return log.bind(audit_log=True)


__all__ = ['observer_factory', 'observer_factory_debug', 'log']


