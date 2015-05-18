"""Tests for :mod:`otter.integration.lib.nova`"""
import json

from testtools.matchers import Equals

from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib import nova
from otter.util.deferredutils import TimedOutError
from otter.util.http import headers


class Response(object):
    """Fake response object"""
    def __init__(self, code):
        self.code = code


def get_fake_treq(test_case, method, url, expected_args_and_kwargs, response):
    """
    Return a fake treq object that would return the given response given
    the correct request made.
    """
    expected_args, expected_kwargs = expected_args_and_kwargs
    response_object, str_response_body = response

    def requester(_url, *args, **kwargs):
        test_case.assertEqual(args, expected_args)
        test_case.assertEqual(kwargs, expected_kwargs)
        test_case.assertEqual(_url, url)
        return succeed(response_object)

    class FakeTreq(object):
        def content(cls, resp):
            test_case.assertEqual(resp, response_object)
            return succeed(str_response_body)

        def json_content(cls, resp):
            test_case.assertEqual(resp, response_object)
            return succeed(json.loads(str_response_body))

    _treq = FakeTreq()

    setattr(_treq, method.lower(), requester)

    return _treq


class _FakeRCS(object):
    endpoints = {'nova': 'novaurl'}
    token = "token"


class NovaServerTestCase(SynchronousTestCase):
    """
    Tests for :class:`NovaServer`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()
        self.rcs = _FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {
            'headers': headers('token'),
            'pool': self.pool
        }

    def get_server(self, method, url, treq_args_kwargs, response, str_body):
        """
        Stub out treq, and return a nova server with
        """
        return nova.NovaServer(id=self.server_id, pool=self.pool,
                               treq=get_fake_treq(self, method, url,
                                                  treq_args_kwargs,
                                                  (response, str_body)))

    def test_delete(self):
        """
        Delete calls the right endpoint and succeeds on 204.
        """
        server = self.get_server('delete', 'novaurl/servers/server_id',
                                 ((), self.expected_kwargs),
                                 Response(204), "delete response")
        d = server.delete(self.rcs)
        self.assertEqual('delete response', self.successResultOf(d))

    def test_list_metadata(self):
        """
        List metadata calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('get', 'novaurl/servers/server_id/metadata',
                                 ((), self.expected_kwargs),
                                 Response(200), '{"metadata": {}}')
        d = server.list_metadata(self.rcs)
        self.assertEqual({'metadata': {}}, self.successResultOf(d))

    def test_update_metadata(self):
        """
        Update metadata calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('put', 'novaurl/servers/server_id/metadata',
                                 (('{"metadata": {}}',),
                                  self.expected_kwargs),
                                 Response(200), '{"metadata": {}}')
        d = server.update_metadata({}, self.rcs)
        self.assertEqual({'metadata': {}}, self.successResultOf(d))

    def test_get_addresses(self):
        """
        Get addresses calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('get', 'novaurl/servers/server_id/ips',
                                 ((), self.expected_kwargs),
                                 Response(200), '{"addresses": {}}')
        d = server.get_addresses(self.rcs)
        self.assertEqual({'addresses': {}}, self.successResultOf(d))


class NovaServerCollectionTestCase(SynchronousTestCase):
    """
    Tests for multi-server api helpers in :mod:`otter.integration.lib.nova`.
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()
        self.rcs = _FakeRCS()

    def test_list_servers(self):
        """
        Get all addresses with a particular name and succeeds on 200.
        """
        treq = get_fake_treq(self, 'get', 'novaurl/servers/detail',
                             ((), {'params': {'limit': 10000},
                                   'headers': headers('token'),
                                   'pool': self.pool}),
                             (Response(200), '{"servers": {}}'))
        d = nova.list_servers(self.rcs, pool=self.pool,
                              _treq=treq)
        self.assertEqual({'servers': {}}, self.successResultOf(d))


class NovaWaitForServersTestCase(SynchronousTestCase):
    """
    Tests for :func:`nova.wait_for_server`.
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        class Group(object):
            group_id = "group_id"

        self.pool = object()
        self.treq = object()
        self.clock = Clock()
        self.rcs = _FakeRCS()
        self.group = Group()
        self.servers = [
            {"metadata": {"rax:autoscale:group:id": "wrong_id"}},
            {"metadata": {}},
        ]

        def _list_servers(rcs, pool, _treq):
            self.assertEqual(rcs, self.rcs)
            self.assertEqual(pool, self.pool)
            self.assertEqual(_treq, self.treq)
            return succeed({'servers': self.servers})

        self.patch(nova, 'list_servers', _list_servers)

        self.wanted = [
            {"metadata": {"rax:autoscale:group:id": "group_id"}}
        ]

    def test_wait_for_servers_retries_until_matcher_matches(self):
        """
        If the matcher does not matches the nova state, retries until it does.
        """
        d = nova.wait_for_servers(self.rcs, self.pool, self.group,
                                  Equals(self.wanted), timeout=5, period=1,
                                  clock=self.clock, _treq=self.treq)
        self.clock.pump((1, 1, 1))
        self.assertNoResult(d)

        self.servers.extend(self.wanted)
        self.clock.pump([1])
        self.assertEqual(self.rcs, self.successResultOf(d))

    def test_wait_for_servers_retries_until_timeout(self):
        """
        If the matcher does not matches the server state, retries until
        it times out.
        """
        d = nova.wait_for_servers(self.rcs, self.pool, self.group,
                                  Equals(self.wanted), timeout=5, period=1,
                                  clock=self.clock, _treq=self.treq)
        self.clock.pump((1, 1, 1, 1, 1))
        self.failureResultOf(d, TimedOutError)
