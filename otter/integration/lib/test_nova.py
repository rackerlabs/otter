"""Tests for :mod:`otter.integration.lib.nova`"""
import json

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.nova import NovaServer
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


class NovaServerTestCase(SynchronousTestCase):
    """
    Tests for :class:`NovaServer`
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()

        class FakeRCS(object):
            endpoints = {'nova': 'novaurl'}
            token = "token"

        self.rcs = FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {
            'headers': headers('token'),
            'pool': self.pool
        }

    def get_server(self, method, url, treq_args_kwargs, response, str_body):
        """
        Stub out treq, and return a nova server with
        """
        return NovaServer(id=self.server_id, pool=self.pool,
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
