"""
Logging intents and performing functions
"""

from functools import partial

import attr

from effect import (
    ComposedDispatcher, Effect, NoPerformerFoundError, TypeDispatcher,
    perform, sync_perform, sync_performer)

from toolz.dicttoolz import merge

from twisted.python.failure import Failure

from txeffect import exc_info_to_failure

from otter.log import log as default_log


@attr.s
class Log(object):
    """
    Intent to log message
    """
    msg = attr.ib()
    fields = attr.ib()


@attr.s(init=False)
class LogErr(object):
    """
    Intent to log error
    """
    failure = attr.ib()
    msg = attr.ib()
    fields = attr.ib()

    def __init__(self, failure, msg, fields):
        # `failure` being `None` means "get the exception from context".
        # We can't wait until the intent is performed to do that, because the
        # exception context will be lost, so we explicitly instantiate a new
        # Failure here.
        if failure is None:
            failure = Failure()
        if type(failure) is tuple:
            failure = exc_info_to_failure(failure)
        self.failure = failure
        self.msg = msg
        self.fields = fields


@attr.s
class GetFields(object):
    """
    Intent to get the fields bound in the effectful context.
    """


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


def get_fields():
    """Return Effect(GetFields())."""
    return Effect(GetFields())


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


def merge_effectful_fields(dispatcher, log):
    """
    Return a log object based on bound fields in the effectful log context and
    the passed-in log. The effectful context takes precedence.

    If log is None then the default otter log will be used.

    Intended for use in legacy-ish intent performers that need a BoundLog.
    """
    log = log if log is not None else default_log
    try:
        eff_fields = sync_perform(dispatcher, get_fields())
    except NoPerformerFoundError:
        # There's no BoundLog wrapping this intent; no effectful log fields to
        # extract
        pass
    else:
        log = log.bind(**eff_fields)
    return log


def get_log_dispatcher(log, fields):
    """
    Get dispatcher containing performers for logging intents that
    use given logger and are bound with given fields
    """
    return TypeDispatcher({
        BoundFields: partial(perform_logging, log, fields, bound_log),
        Log: partial(perform_logging, log, fields, log_msg),
        LogErr: partial(perform_logging, log, fields, log_err),
        GetFields: sync_performer(lambda d, i: fields),
    })
