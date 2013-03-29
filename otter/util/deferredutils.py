"""
Deferred utilities
"""

from twisted.internet import defer


def unwrap_first_error(possible_first_error):
    """
    Failures returned by :method:`defer.gatherResults` are failures that wrap
    a defer.FirstError, which wraps the inner failure.

    Checks failure to see if it is a defer.FirstError.  If it is, recursively
    gets the underlying failure that it wraps (in case it is a first error
    wrapping a first error, etc.)

    :param possible_first_error: a failure that may wrap a
        :class:`defer.FirstError`
    :type possible_first_error: :class:`Failure`

    :return: :class:`Failure` that is under any/all the
        :class:`defer.FirstError`s
    """
    if possible_first_error.check(defer.FirstError):
        return unwrap_first_error(possible_first_error.value.subFailure)
    return possible_first_error  # not a defer.FirstError
