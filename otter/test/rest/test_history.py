"""
Tests for `otter.rest.history`
"""
import json

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.test.rest.request import RestAPITestMixin, request
from otter.util.config import set_config_data


class OtterHistoryTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/history``
    """
    tenant_id = '101010'
    endpoint = '/v1.0/101010/history'

    invalid_methods = ("DELETE", "PUT", "POST")

    def setUp(self):
        """Set an elastic search config var."""
        super(OtterHistoryTestCase, self).setUp()
        set_config_data({'elasticsearch': {'host': "http://dummy/search"}})

    @mock.patch('otter.rest.history.treq')
    def test_history(self, treq):
        """
        the history api endpoint returns the items from the audit log
        """
        data = json.dumps({'abc': 'def'})
        response = mock.Mock(code=200)

        def get(*args, **kwargs):
            return defer.succeed(response)
        treq.get.side_effect = get

        def content(*args, **kwargs):
            return defer.succeed(data)
        treq.content.side_effect = content

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        self.assertEqual(200, result.response.code)
        self.assertEqual(data, result.content)

        treq.get.assert_called_once_with('http://dummy/search')
        treq.content.assert_called_once_with(response)
