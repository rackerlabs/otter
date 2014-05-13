"""
Mixins and utilities to be used for testing.
"""
import json
import mock
import os
import treq

from twisted.internet import defer
from twisted.python.failure import Failure
from zope.interface import directlyProvides

from otter.log.bound import BoundLog


class matches(object):
    """
    A helper for using `testtools matchers
    <http://testtools.readthedocs.org/en/latest/for-test-authors.html#matchers>`_
    with mock.

    It allows testtools matchers to be used in places where comparisons for
    equality would normally be used, such as the ``mock.Mock.assert_*``
    methods.

    Example::

        mock_fun({'foo': 'bar', 'baz': 'bax'})
        mock_fun.assert_called_once_with(
            matches(
                ContainsDict(
                    {'baz': Equals('bax')})))

    See `testtools.matchers
    <http://mumak.net/testtools/apidocs/testtools.matchers.html>`_
    for a complete list of matchers provided with testtools.

    :param matcher: A testtools matcher that will be matched when this object
        is compared to another object.
    """
    def __init__(self, matcher):
        self._matcher = matcher

    def __eq__(self, other):
        return self._matcher.match(other) is None

    def __ne__(self, other):
        return self != other

    def __str__(self):
        return str(self._matcher)

    def __repr__(self):
        return 'matches({0!s}'.format(self._matcher)


class CheckFailure(object):
    """
    Class that can be passed to an `assertEquals` or `assert_called_with` -
    shortens checking whether a `twisted.python.failure.Failure` wraps an
    Exception of a particular type.
    """
    def __init__(self, exception_type):
        self.exception_type = exception_type

    def __eq__(self, other):
        return isinstance(other, Failure) and other.check(
            self.exception_type)


def fixture(fixture_name):
    """
    :param fixture_name: The base filename of the fixture, ex: simple.atom.
    :type: ``bytes``

    :returns: ``bytes``
    """
    return open(os.path.join(
        os.path.dirname(__file__),
        'fixtures',
        fixture_name
    )).read()


def iMock(*ifaces, **kwargs):
    """
    Creates a mock object that provides a particular interface.

    :param iface: the interface to provide
    :type iface: :class:``zope.interface.Interface``

    :returns: a mock object that is specced to have the attributes and methods
        as a provider of the interface
    :rtype: :class:``mock.MagicMock``
    """
    if 'spec' in kwargs:
        del kwargs['spec']

    all_names = [name for iface in ifaces for name in iface.names()]

    imock = mock.MagicMock(spec=all_names, **kwargs)
    directlyProvides(imock, *ifaces)
    return imock


def patch(testcase, *args, **kwargs):
    """
    Patches and starts a test case, taking care of the cleanup.
    """
    if not getattr(testcase, '_stopallAdded', False):
        testcase.addCleanup(mock.patch.stopall)
        testcase._stopallAdded = True

    return mock.patch(*args, **kwargs).start()


class SameJSON(object):
    """
    Compare an expected decoded JSON structure to a string of JSON by
    decoding the input string and comparing the resulting structure to our
    expected structure.

    Example::

        foo.assert_called_once_with(SameJSON({'success': True}))
    """
    def __init__(self, expected):
        """
        :param expected: The expected result of JSON decoding.
        """
        self._expected = expected

    def __eq__(self, other):
        """
        :param str other: A string of JSON that will be decoded and compared
            to our expected structure.

        :return: `True` if the the result of decoding `other` compares equal
            to our expected structure, otherwise `False`
        :rtype: bool
        """
        return self._expected == json.loads(other)

    def __repr__(self):
        """
        repr containing the expected object.
        """
        return 'SameJSON({0!r})'.format(self._expected)


class LockMixin(object):
    """
    A mixin for patching BasicLock.
    """

    def mock_lock(acquire_result=None, release_result=None):
        """
        :param acquire_result: A value to be returned by acquire.
        :param release_result: A value to be returned by release.

        :return: A mock Lock instance.
        """
        lock = mock.Mock(spec=['acquire', 'release', '_acquire'])

        def _acquire(*args, **kwargs):
            return defer.succeed(acquire_result)
        lock.acquire.side_effect = _acquire
        lock._acquire = lock.acquire

        def _release():
            return defer.succeed(release_result)
        lock.release.side_effect = _release
        return lock


class DeferredFunctionMixin(object):
    """
    A mixin for adding functions that return specific values
    """

    def setup_func(self, func):
        """
        Setup `func` to return value from self.returns
        """

        def mock_func(*args, **kwargs):
            ret = self.returns.pop(0)
            if isinstance(ret, Exception):
                return defer.fail(ret)
            return defer.succeed(ret)

        func.side_effect = mock_func


class StubLog(object):
    """
    A fake BoundLog-like object that records log messages and binds in a way
    that is easily testable.

    :ivar binds: A dictionary of values bound to this log.
    :ivar msgs: A record of calls to :func:`StubLog.msg`.
    :ivar errs: A record of calls to :func:`StubLog.err`.
    """
    def __init__(self, binds=None):
        self.binds = binds if binds is not None else {}
        self.msgs = []
        self.errs = []

    def bind(self, **kwargs):
        """
        Return a new :class:`StubLog` with the given binds.
        """
        kwargs.update(self.binds)
        return StubLog(kwargs)

    def msg(self, *args, **kwargs):
        self.msgs.append((args, kwargs))

    def err(self, *args, **kwargs):
        self.errs.append((args, kwargs))


def mock_log(*args, **kwargs):
    """
    Returns a BoundLog whose msg and err methods are mocks.  Makes it easier
    to test logging, since instead of making a mock object and testing::

        log.bind.return_value.msg.assert_called_with(...)

    This can be done instead::

        log.msg.assert_called_with(mock.ANY, bound_value1="val", ...)

    Since in all likelyhood, testing that certain values are bound would be more
    important than testing the exact logged message.
    """
    return BoundLog(mock.Mock(spec=[]), mock.Mock(spec=[]))


class StubResponse(object):
    """
    A fake pre-built Twisted Web Response object.
    """
    def __init__(self, code, content, headers):
        self.code = code
        self.content = content
        self.headers = headers


class StubTreq(object):
    """
    An object that looks like :module:`treq`.

    :ivar requests: A list of request arguments.
    :param response: A premade response to return from all requests.
    """
    def __init__(self, response):
        self._response = response
        self.requests = []

    def json_content(self, response):
        return self.content(response).addCallback(json.loads)

    def content(self, response):
        return defer.succeed(response.content)

    def _request(self, method, url, headers=None, data=None, log=None):
        self.requests.append({'method': method, 'url': url,
                              'headers': headers,
                              'data': data, 'log': log})
        return defer.succeed(self._response)

    def get(self, *args, **kwargs):
        return self._request('get', *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._request('post', *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._request('put', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._request('delete', *args, **kwargs)


def stub_treq(code, content, headers=None):
    """
    Return a :class:`StubTreq` that always returns the same response.
    """
    treq = StubTreq(StubResponse(code, content, headers))
    return treq


def mock_treq(code=200, json_content={}, method='get', content='', treq_mock=None):
    """
    Return mocked treq instance configured based on arguments given

    :param code: HTTP response code
    :param json_content: A dict to be returned from treq.json_content
    :param method: HTTP method
    :param content: Str to be returned from treq.content
    """
    if treq_mock is None:
        treq_mock = mock.MagicMock(spec=treq)
    response = mock.MagicMock(code=code)
    treq_mock.configure_mock(**{method + '.return_value': defer.succeed(response)})
    treq_mock.json_content.return_value = defer.succeed(json_content)
    treq_mock.content.return_value = defer.succeed(content)
    return treq_mock


class DummyException(Exception):
    """
    Fake exception
    """
