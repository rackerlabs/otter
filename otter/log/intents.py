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
    """
    Return Effect of BoundFields used to wrap effect with fields passed as
    keyword arguments
    """
    return Effect(BoundFields(effect, fields))


def msg(msg, **fields):
    """
    Return Effect of Log
    """
    return Effect(Log(msg, fields))


def err(failure, msg, **fields):
    """
    Return Effect of LogErr
    """
    return Effect(LogErr(failure, msg, fields))


def perform_logging(log, fields, log_func, disp, intent, box):
    """ Perform logging related intents """
    all_fields = merge(fields, intent.fields)
    log_func(log, all_fields, disp, intent, box)


def log_msg(log, all_fields, disp, intent, box):
    """ Perform Log intent """
    log.msg(intent.msg, **all_fields)
    box.succeed(None)


def log_err(log, all_fields, disp, intent, box):
    """ Perform LogErr intent """
    log.err(intent.failure, intent.msg, **all_fields)
    box.succeed(None)


def bound_log(log, all_fields, disp, intent, box):
    """ Perform BoundFields intent """
    new_disp = ComposedDispatcher(
        [get_log_dispatcher(log, all_fields), disp])
    perform(new_disp, intent.effect.on(box.succeed, box.fail))


def get_log_dispatcher(log, fields):
    """
    Get dispatcher containing performers for logging intents that
    use given logger and are bound with given fields
    """
    return TypeDispatcher({
        BoundFields: partial(perform_logging, log, fields, bound_log),
        Log: partial(perform_logging, log, fields, log_msg),
        LogErr: partial(perform_logging, log, fields, log_err)
    })
