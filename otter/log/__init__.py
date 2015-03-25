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


class Log(object):
    def __init__(self, msg, **fields):
        self.msg = msg
        self.fields = feilds


@attributes(['bound_log', 'effect'])
class BoundLogIntent(object):
    pass


def perform_bound_logging(bound_intent, box):

    @sync_performer
    def scoped_performer(dispatcher, log_intent):
        bound_intent.bound_log.msg(log_intent.message, **log_intent.fields)

    new_disp = ComposedDispatcher([
        TypeDispatcher({Log: scoped_performer}),
        dispatcher])
    perform(new_disp, bound_intent.effect.on(box.succeed, box.fail))


def get_log_dispatcher():
    return TypeDispatcher({LogScope: perform_bound_logging})
