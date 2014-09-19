"""Tests for convergence."""

import mock
import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import succeed, fail

from otter.test.utils import StubTreq, StubResponse, patch
from otter.util.http import headers
from otter.convergence import (
    get_all_server_details, get_scaling_group_servers)


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        self.clock = Clock()
        self.auth = mock.Mock(spec=['authenticate_tenant'])
        self.auth.authenticate_tenant.return_value = succeed(('token', 'catalog'))
        self.peu = patch(self, 'otter.convergence.public_endpoint_url',
                         return_value='url')
        self.req = ('GET', 'url/servers/detail?limit=10', headers('token'), None, {})
        self.resp = StubResponse(200, {})
        #self.treq = StubTreq({req: self.resp}, {self.resp: '{}'})

    def test_get_all_less_limit(self):
        """
        `get_all_server_details` will not fetch again if first get returns results
        with size < limit
        """
        servers = [{'id': i} for i in range(9)]
        treq = StubTreq([(self.req, self.resp)],
                        [(self.resp, json.dumps({'servers': servers}))])
        d = get_all_server_details('tid', self.auth, 'service', 'ord',
                                   limit=10, clock=self.clock, _treq=treq)
        self.assertEqual(self.successResultOf(d), servers)

    def test_get_all_above_limit(self):
        """
        `get_all_server_details` will fetch again until batch returned has size < limit
        """

