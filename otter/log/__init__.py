"""
Package for all otter specific logging functionality.
"""

from otter.log.setup import observer_factory, observer_factory_debug
from otter.log.bound import BoundLog

from toolz.dicttoolz import merge

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


class LogErr(object):
    def __init__(self, failure, msg, **fields):
        self.failure = failure
        self.msg = msg
        self.fields = fields


class BoundLog(object):
    def __init__(self, effect, **feilds):
        self.effect = effect
        self.fields = fields


def perform_logging(log, fields, disp, intent, box):
    all_fields = merge(fields, intent.fields)
    if type(intent) is Log:
        log.msg(intent.msg, **all_fields)
        box.succeed(None)
    elif type(intent) is LogErr:
        log.err(intent.failure, intent.msg, **all_fields)
        box.succeed(None)
    elif type(intent) is BoundLog:
        new_disp = ComposedDispatcher(
            [get_log_dispatcher(log, all_fields), disp])
        perform(new_disp, intent.effect.on(box.succeed, box.fail))


def get_log_dispatcher(log, fields):
    return TypeDispatcher({
        BoundLog: partial(perform_logging, log, fields),
        Log: partial(perform_logging, log, fields)
        LogErr: partial(perform_logging, log, fields)
    })
