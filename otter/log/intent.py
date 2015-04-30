"""
Logging intents and performing functions
"""

from functools import partial

from characteristic import attributes

from effect import ComposedDispatcher, Effect, TypeDispatcher, perform

from toolz.dicttoolz import merge


@attributes(['msg', 'fields'])
class Log(object):
    """
    Intent to log message
    """


@attributes(['failure', 'msg', 'fields'])
class LogErr(object):
    """
    Intent to log error
    """


@attributes(['effect', 'fields'])
class BoundFields(object):
    """
    Intent that binds log fields to an effect. Any log or err effect
    found when performing given effect will be expanded with these fields
    """


def with_log(effect, **fields):
    return Effect(BoundFields(effect=effect, fields=fields))


def msg(msg, **fields):
    return Effect(Log(msg=msg, fields=fields))


def err(failure, msg, **fields):
    return Effect(LogErr(failure=failure, msg=msg, fields=fields))


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
