"""
Logging intents and performing functions
"""

from functools import partial

import attr

from effect import ComposedDispatcher, Effect, TypeDispatcher, perform

from toolz.dicttoolz import merge


@attr.s
class Log(object):
    """
    Intent to log message
    """
    msg = attr.ib()
    fields = attr.ib()


@attr.s
class LogErr(object):
    """
    Intent to log error
    """
    failure = attr.ib()
    msg = attr.ib()
    fields = attr.ib()


@attr.s
class BoundFields(object):
    """
    Intent that binds log fields to an effect. Any log or err effect
    found when performing given effect will be expanded with these fields
    """
    effect = attr.ib()
    fields = attr.ib()


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
