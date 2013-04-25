import functools
from twisted.python.constants import Names, NamedConstant


class BoundLog(object):
    def __init__(self, msg, err):
        self.msg = msg
        self.err = err

    def bind(self, **kwargs):
        msg = functools.partial(self.msg, **kwargs)
        err = functools.partial(self.err, **kwargs)

        return self.__class__(msg, err)


class Levels(Names):
    DEBUG = NamedConstant()
    INFO = NamedConstant()
    ERROR = NamedConstant()
    WARNING = NamedConstant()


class TwiggyLog(object):
    def __init__(self, boundLog, error=None):
        self._boundLog = boundLog
        self._error = error

    def fields(self, **kwargs):
        return self.__class__(self._boundLog.bind(**kwargs), self._error)

    def name(self, name):
        return self.fields(system=name)

    def _msg(self, level, msg, **kwargs):
        kwargs.update(level=level.name)
        self._boundLog.msg(format=msg, **kwargs)

    def info(self, msg, **kwargs):
        self._msg(Levels.INFO, msg, **kwargs)

    def warn(self, msg, **kwargs):
        self._msg(Levels.WARNING, msg, **kwargs)

    def trace(self, exceptionOrFailure):
        return self.__class__(self._boundLog, exceptionOrFailure)

    def error(self, msg, **kwargs):
        kwargs.update(level=Levels.ERROR)
        if self._error is not None:
            self._boundLog.err(self._error, msg, **kwargs)
        else:
            self._boundLog.err(_why=msg, format=msg, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self._msg(Levels.DEBUG, msg, *args, **kwargs)

    def struct(self, **kwargs):
        self.info('')

if __name__ == '__main__':
    import sys
    from twisted.python import log

    log.startLogging(sys.stdout)

    l = TwiggyLog(BoundLog(log.msg, log.err))
    l.fields(foo='bar').info("foo %(foo)s")
    l.info('foo')
    l.name('testing').fields(foo="bar").info("[%(level)s] Wat?")

    try:
        raise Exception("OH NOES")
    except Exception as e:
        l.trace(e).error("UH OH")
