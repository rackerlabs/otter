"""
Logging intents and performing functions
"""

from functools import partial

from effect import ComposedDispatcher, Effect, TypeDispatcher, perform

from toolz.dicttoolz import merge


class Log(object):
    """
    Intent to log message
    """
    def __init__(self, msg, fields):
        self.msg = msg
        self.fields = fields


class LogErr(object):
    """
    Intent to log error
    """
    def __init__(self, failure, msg, fields):
        self.failure = failure
        self.msg = msg
        self.fields = fields


class BoundFields(object):
    """
    Intent that binds log fields to an effect. Any log or err effect
    found when performing given effect will be expanded with these fields
    """
    def __init__(self, effect, fields):
        self.effect = effect
        self.fields = fields


def with_log(effect, **fields):
    return Effect(BoundFields(effect, fields))


def msg(msg, **fields):
    return Effect(Log(msg, fields))


def err(failure, msg, **fields):
    return Effect(LogErr(failure, msg, fields))


def perform_logging(log, fields, disp, intent, box):
    all_fields = merge(fields, intent.fields)
    if type(intent) is Log:
        log.msg(intent.msg, **all_fields)
        box.succeed(None)
    elif type(intent) is LogErr:
        log.err(intent.failure, intent.msg, **all_fields)
        box.succeed(None)
    elif type(intent) is BoundFields:
        new_disp = ComposedDispatcher(
            [get_log_dispatcher(log, all_fields), disp])
        perform(new_disp, intent.effect.on(box.succeed, box.fail))
    else:
        raise RuntimeError('Called perform_logging on {}'.format(intent))


def get_log_dispatcher(log, fields):
    return TypeDispatcher({
        BoundFields: partial(perform_logging, log, fields),
        Log: partial(perform_logging, log, fields),
        LogErr: partial(perform_logging, log, fields)
    })
