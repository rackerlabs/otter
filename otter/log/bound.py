"""
Utility for doing bound logging with twisted.
"""

import functools


DEBUG = 7


class BoundLog(object):
    """
    BoundLog manages a partially applied copy of msg and err.

    :ivar msg: The function to call for logging non-error messages.
    :ivar err: The function to call for logging errors.
    """
    def __init__(self, msg, err):
        self.msg = msg
        self.err = err

    def bind(self, **kwargs):
        """
        Bind the keyword arguments to `self.msg` and `self.err`.

        :params dict kwargs:  Keyword arguments accepted by :py:func:`log.msg`
            and :py:func:`log.err`.
        :returns: A new :py:class:`BoundLog` instance.
        :rtype: BoundLog
        """
        msg = functools.partial(self.msg, **kwargs)
        err = functools.partial(self.err, **kwargs)

        return self.__class__(msg, err)

    def debug(self, msg, **kwargs):
        """
        Log the message as debug message by calling `self.msg` with level=DEBUG

        :param str msg: message to be logged
        :param dict **kwargs: Keyword arguments accepted by :py:func:`log.msg`
        """
        return self.msg(msg, level=DEBUG, **kwargs)
