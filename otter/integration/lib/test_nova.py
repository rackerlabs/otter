"""Tests for :mod:`otter.integration.lib.nova`"""
import json

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.nova import NovaServer


class _Response(object):
    """Fake response object"""
    def __init__(self, code):
        self.code = code


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

    def get_server(self, method, url, treq_args_kwargs, response, str_body):
        """
        Stub out treq, and return a nova server with
        """
        def requester(_url, *args, **kwargs):
            self.assertEqual(["token"],
                             kwargs.get('headers', {}).get('x-auth-token'))
            self.assertEqual(self.pool, kwargs.get('pool'))
            kwargs.pop('headers')
            kwargs.pop('pool')

            if url == _url and (args, kwargs) == treq_args_kwargs:
                return succeed(response)
            self.fail(
                "Expected a request to {} with args and kwargs: {}\n "
                "Got a request to {} with args and kwargs: {}."
                .format(url, treq_args_kwargs, _url, (args, kwargs)))

        class FakeTreq(object):
            def content(cls, resp):
                return succeed(str_body)

            def json_content(cls, resp):
                return succeed(json.loads(str_body))

        _treq = FakeTreq()
        setattr(_treq, method, requester)

        return NovaServer(id=self.server_id, pool=self.pool, treq=_treq)

    def test_delete(self):
        """
        Delete calls the right endpoint and succeeds on 204.
        """
        server = self.get_server('delete', 'novaurl/servers/server_id',
                                 ((), {}), _Response(204), "delete response")
        d = server.delete(self.rcs)
        self.assertEqual('delete response', self.successResultOf(d))

    def test_list_metadata(self):
        """
        List metadata calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('get', 'novaurl/servers/server_id/metadata',
                                 ((), {}), _Response(200), '{"metadata": {}}')
        d = server.list_metadata(self.rcs)
        self.assertEqual({'metadata': {}}, self.successResultOf(d))

    def test_update_metadata(self):
        """
        Update metadata calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('put', 'novaurl/servers/server_id/metadata',
                                 (('{"metadata": {}}',), {}), _Response(200),
                                 '{"metadata": {}}')
        d = server.update_metadata({}, self.rcs)
        self.assertEqual({'metadata': {}}, self.successResultOf(d))

    def test_get_addresses(self):
        """
        Get addresses calls the right endpoint and succeeds on 200.
        """
        server = self.get_server('get', 'novaurl/servers/server_id/ips',
                                 ((), {}), _Response(200),
                                 '{"addresses": {}}')
        d = server.get_addresses(self.rcs)
        self.assertEqual({'addresses': {}}, self.successResultOf(d))
