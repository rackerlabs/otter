"""
Deferred utilities
"""

from twisted.internet import defer


def unwrap_first_error(possible_first_error):
    """
    Failures returned by :meth:`defer.gatherResults` are failures that wrap
    a :class:`defer.FirstError`, which wraps the inner failure.

    Checks failure to see if it is a defer.FirstError.  If it is, recursively
    gets the underlying failure that it wraps (in case it is a first error
    wrapping a first error, etc.)

    :param possible_first_error: a failure that may wrap a
        :class:`defer.FirstError`
    :type possible_first_error: :class:`Failure`

    :return: :class:`Failure` that is under any/all the :class:`defer.FirstError`
    """
    if possible_first_error.check(defer.FirstError):
        return unwrap_first_error(possible_first_error.value.subFailure)
    return possible_first_error  # not a defer.FirstError


def ignore_and_log(failure, exception_type, log, msg):
    """
    Ignore the given exception type and log it. This method is to be used as errback handler

    :param failure: `Failure` instance representing the error
    :param exception_type: Exception class that needs to be trapped
    :param log: A bound logger
    :param msg: message to be logged

    :return: None if exception is trapped. Otherwise, raises other error
    """
    failure.trap(exception_type)
    log.msg(msg, reason=failure)
