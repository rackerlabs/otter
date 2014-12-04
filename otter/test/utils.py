"""
Mixins and utilities to be used for testing.
"""
from functools import partial
import json
import mock
import os
import treq

from zope.interface import implementer, directlyProvides
from zope.interface.verify import verifyObject

from testtools.matchers import Mismatch, MatchesException

from twisted.internet import defer
from twisted.internet.defer import succeed, Deferred, maybeDeferred
from twisted.python.failure import Failure
from twisted.application.service import Service

from otter.log.bound import BoundLog
from otter.supervisor import ISupervisor
from otter.models.interface import IScalingGroup
from otter.util.deferredutils import DeferredPool

from pyrsistent import freeze


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


class Provides(object):
    """
    Match if instance provides given interface
    """
    def __init__(self, intf):
        self.intf = intf

    def __str__(self):
        return 'Provides {}'.format(self.intf)

    def match(self, inst):
        """
        Return None if inst provides given interface. Otherwise return Mismatch
        """
        return None if verifyObject(self.intf, inst) else Mismatch(
            'Expected instance providing interface {}'.format(self.intf))


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


class CheckFailureValue(object):
    """
    Class whose instances compare equal to a Failure wrapping an equivalent
    exception, based on :obj:`MatchesException`.
    """
    def __init__(self, exception):
        self.exception = exception

    def __repr__(self):
        return "CheckFailureValue(%r)" % (self.exception,)

    def __eq__(self, other):
        matcher = MatchesException(self.exception)
        return (isinstance(other, Failure)
                and other.check(type(self.exception)) is not None
                and matcher.match((type(other.value), other.value, None)) is None)


class IsCallable(object):
    """
    Class that can be used in tests that checks if given argument is callable
    """
    def __eq__(self, other):
        return callable(other)


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
    def __init__(self, code, headers, data=None):
        self.code = code
        self.headers = headers
        # Data is not part of twisted response object
        self._data = data


def stub_pure_response(body, code=200, response_headers=None):
    """
    Return the type of two-tuple response that pure_http.Request returns.
    """
    if isinstance(body, dict):
        body = json.dumps(body)
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
        :param reqs: A dictionary specifying the values that the `request`
            method should return. Keys are tuples of:
            (method, url, headers, data, (<other key names>)).
            Since headers is usually passed as a dict, here it should be
            specified as a tuple of two-tuples in sorted order.

        :param contents: A dictionary specifying the values that the `content`
            method should return. Keys should match up with the values of the
            `reqs` dict.
        """
        _check_unique_keys(reqs)
        _check_unique_keys(contents)
        self.reqs = reqs
        self.contents = contents

    def request(self, method, url, **kwargs):
        """
        Return a result by looking up the arguments in the `reqs` dict.
        The only kwargs we care about are 'headers' and 'data',
        although if other kwargs are passed their keys count as part of the
        request.

        'log' would also be a useful kwarg to check, but since dictionary keys
        should be immutable, and it's hard to get the exact instance of
        BoundLog, that's being ignored for now.
        """
        key = (method, url, kwargs.pop('headers', None),
               kwargs.pop('data', None), kwargs)
        return succeed(alist_get(self.reqs, key))

    def content(self, response):
        """Return a result by looking up the response in the `contents` dict."""
        return succeed(alist_get(self.contents, response))

    def json_content(self, response):
        """Return :meth:`content` after json-decoding"""
        return self.content(response).addCallback(json.loads)

    def put(self, url, data=None, **kwargs):
        """
        Syntactic sugar for making a PUT request, because the order of the
        params are different than :meth:`request`
        """
        return self.request('PUT', url, data=data, **kwargs)

    def post(self, url, data=None, **kwargs):
        """
        Syntactic sugar for making a POST request, because the order of the
        params are different than :meth:`request`
        """
        return self.request('POST', url, data=data, **kwargs)

    def __getattr__(self, method):
        """
        Syntactic sugar for making head/get/delete requests, because the order
        of parameters is the same as :meth:`request`
        """
        if method in ('get', 'head', 'delete'):
            return partial(self.request, method.upper())
        raise AttributeError("StubTreq has no attribute '{0}'".format(method))

    def __str__(self):
        return 'StubTreq; requests: {}, contents: {}'.format(
            self.reqs, self.contents)


class StubTreq2(object):
    """
    A stub version of otter.utils.logging_treq that returns canned responses
    from dictionaries.

    It tries to be simpler from above `StubTreq` based on its arguments. It correlates
    requests keeping track of Twisted response objects internally. Its also simpler
    because it doesn't expect immuatable args
    """
    def __init__(self, reqs=None):
        """
        :param reqs: A list of 2-item tuple containing (method, url, <kwargs dict>)
            as first item. The second item is either (response code, response data)
            tuple or list of these tuples. When it is list, each `request` call with
            same args will return first popped element

        'log' would also be a useful kwarg to check, but since dictionary keys
        should be immutable, and it's hard to get the exact instance of
        BoundLog, that's being ignored for now.
        """
        self.reqs = {}
        if reqs is not None:
            for (method, url, kwargs), response in reqs:
                kwargs.pop('log', None)
                self.reqs[freeze((method, url, kwargs))] = response

    def request(self, method, url, **kwargs):
        """
        Return a result by looking up the arguments in the `reqs` dict.
        The only kwargs we care about are 'headers' and 'data',
        although if other kwargs are passed their keys count as part of the
        request.
        """
        kwargs.pop('log', None)
        resp = self.reqs[freeze((method, url, kwargs))]
        if isinstance(resp, list):
            code, data = resp.pop(0)
        else:
            code, data = resp
        return succeed(StubResponse(code, (), data))

    def content(self, response):
        """Return a result by taking the data from `response` itself."""
        return succeed(response._data)

    def json_content(self, response):
        """Return :meth:`content` after json-decoding"""
        return self.content(response).addCallback(json.loads)

    def put(self, url, data=None, **kwargs):
        """
        Syntactic sugar for making a PUT request, because the order of the
        params are different than :meth:`request`
        """
        return self.request('PUT', url, data=data, **kwargs)

    def post(self, url, data=None, **kwargs):
        """
        Syntactic sugar for making a POST request, because the order of the
        params are different than :meth:`request`
        """
        return self.request('POST', url, data=data, **kwargs)

    def __getattr__(self, method):
        """
        Syntactic sugar for making head/get/delete requests, because the order
        of parameters is the same as :meth:`request`
        """
        if method in ('get', 'head', 'delete'):
            return partial(self.request, method.upper())
        raise AttributeError("StubTreq has no attribute '{0}'".format(method))

    def __str__(self):
        return 'StubTreq; requests: {}'.format(self.reqs)


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
    treq_mock.json_content.side_effect = lambda r: defer.succeed(json_content)
    treq_mock.content.side_effect = lambda r: defer.succeed(content)
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

    def __init__(self, *args, **kwargs):
        """
        Initialize the fake supervisor.
        """
        self.args = args
        self.deferred_pool = DeferredPool()
        self.exec_calls = []
        self.exec_defs = []
        self.del_index = 0
        self.del_calls = []
        self.scrub_calls = []
        self.scrub_defs = []

    def execute_config(self, log, transaction_id, scaling_group, launch_config):
        """
        Execute single launch config
        """
        self.exec_calls.append((log, transaction_id, scaling_group, launch_config))
        self.exec_defs.append(Deferred())
        return self.exec_defs[-1]

    def execute_delete_server(self, log, transaction_id, scaling_group, server):
        """
        Delete server
        """
        self.del_index += 1
        self.del_calls.append((log, transaction_id, scaling_group, server))
        return succeed(self.del_index)

    def scrub_otter_metadata(self, log, transaction_id, tenant_id, server_id):
        """
        Scrubs otter-specific metadata off a server.
        """
        self.scrub_calls.append((log, transaction_id, tenant_id, server_id))
        return succeed(None)


def mock_group(state, tenant_id='tenant', group_id='group'):
    """
    Return mocked `IScalingGroup` that has tunable `modify_state` method

    :param state: This will be passed to `modify_state` callable
    """
    group = iMock(IScalingGroup, tenant_id=tenant_id, uuid=group_id)
    group.pause_modify_state = False
    group.modify_state_values = []

    def fake_modify_state(f, *args, **kwargs):
        d = maybeDeferred(f, group, state, *args, **kwargs)
        d.addCallback(lambda r: group.modify_state_values.append(r) or r)
        if group.pause_modify_state:
            group.modify_state_pause_d = Deferred()
            return group.modify_state_pause_d.addCallback(lambda _: d)
        else:
            return d

    group.modify_state.side_effect = fake_modify_state
    return group


def _check_unique_keys(data):
    """Check that all the keys in an association list are unique."""
    # O(lol)
    for itemindex, item in enumerate(data):
        for itemagain in data[itemindex + 1:]:
            if item[0] == itemagain[0]:
                raise Exception("Duplicate items in EQDict: %r:%r and %r:%r"
                                % (item[0], item[1], itemagain[0], itemagain[1]))


def alist_get(data, key):
    """Look up a value in an association list."""
    for dkey, dvalue in data:
        if dkey == key:
            return dvalue
    raise KeyError(key)
