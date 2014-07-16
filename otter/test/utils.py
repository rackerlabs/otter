"""
Mixins and utilities to be used for testing.
"""
import json
import mock
import os
import treq

from zope.interface import implementer, directlyProvides

from testtools.matchers import Mismatch

from twisted.internet import defer
from twisted.internet.defer import succeed, Deferred
from twisted.python.failure import Failure
from twisted.application.service import Service

from otter.log.bound import BoundLog
from otter.supervisor import ISupervisor


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
        self._last_match = None

    def __eq__(self, other):
        self._last_match = self._matcher.match(other)
        return self._last_match is None

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return str(self._matcher)

    def __repr__(self):
        if self._last_match:
            return 'matches({}): <mismatch: {}>'.format(self._matcher, self._last_match.describe())
        else:
            return 'matches({0!s})'.format(self._matcher)


class IsBoundWith(object):
    """
    Match if BoundLog is bound with given args
    """
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __str__(self):
        return 'IsBoundWith {}'.format(self.kwargs)

    def match(self, log):
        """
        Return None if log is bound with given args/kwargs. Otherwise return Mismatch
        """
        if not isinstance(log, BoundLog):
            return Mismatch('log is not a BoundLog')
        # Collect kwargs
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
        [kwargs.update(kwa) for kwa in reversed(kwargs_list)]
        # Compare and return accordingly
        if self.kwargs == kwargs:
            return None
        else:
            return Mismatch('Expected kwargs {} but got {} instead'.format(self.kwargs, kwargs))


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


def mock_log(*args, **kwargs):
    """
    Returns a BoundLog whose msg and err methods are mocks.  Makes it easier
    to test logging, since instead of making a mock object and testing::

        log.bind.return_value.msg.assert_called_with(...)

    This can be done instead::

        log.msg.assert_called_with(mock.ANY, bound_value1="val", ...)

    Since in all likelyhood, testing that certain values are bound would be
    more important than testing the exact logged message.
    """
    return BoundLog(mock.Mock(spec=[]), mock.Mock(spec=[]))


class StubResponse(object):
    """
    A fake pre-built Twisted Web Response object.
    """
    def __init__(self, code, headers):
        self.code = code
        self.headers = headers


def stub_pure_response(body, code=200, response_headers=None):
    """
    Return the type of two-tuple response that pure_http.Request returns.
    """
    if response_headers is None:
        response_headers = {}
    return (StubResponse(code, response_headers), body)


class StubTreq(object):
    """
    A stub version of otter.utils.logging_treq that returns canned responses
    from dictionaries.
    """
    def __init__(self, reqs=None, contents=None):
        """
        :param reqs: A dictionary specifying the values that the `request` method should return. Keys
            are tuples of (method, url, headers, data, log). Since headers is usually passed as a dict,
            here it should be specified as a tuple of two-tuples in sorted order.
        :param contents: A dictionary specifying the values that the `content` method should return.
            Keys should match up with the values of the `reqs` dict.
        """
        self.reqs = reqs
        self.contents = contents

    def request(self, method, url, headers, data, log):
        """Return a result by looking up the arguments in the `reqs` dict."""
        if headers is not None:
            headers = tuple(sorted(headers.items()))
        return self.reqs[(method, url, headers, data, log)]

    def content(self, response):
        """Return a result by looking up the response in the `contents` dict."""
        return self.contents[response]


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


@implementer(ISupervisor)
class FakeSupervisor(object, Service):
    """
    A fake supervisor that keeps track of calls made
    """

    def __init__(self, *args):
        self.args = args
        self.index = 0
        self.exec_calls = []
        self.exec_defs = []
        self.del_index = 0
        self.del_calls = []

    def execute_config(self, log, transaction_id, scaling_group, launch_config):
        """
        Execute single launch config
        """
        self.index += 1
        self.exec_calls.append((log, transaction_id, scaling_group, launch_config))
        d = Deferred()
        self.exec_defs.append(d)
        return succeed((self.index, d))

    def execute_delete_server(self, log, transaction_id, scaling_group, server):
        """
        Delete server
        """
        self.del_index += 1
        self.del_calls.append((log, transaction_id, scaling_group, server))
        return succeed(self.del_index)
