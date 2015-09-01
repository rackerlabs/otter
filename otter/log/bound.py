"""
Utility for doing bound logging with twisted.
"""

import functools


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


def bound_log_kwargs(log):
    """
    Return keyword arguments bound to given logger
    """
    f = log.msg
    kwargs_list = []
    while True:
        try:
            kwargs_list.append(f.keywords)
        except AttributeError:
            break
        else:
            f = f.func
    # combine them in order they were bound
    kwargs = {}
    for kwa in reversed(kwargs_list):
        kwargs.update(kwa)
    return kwargs
