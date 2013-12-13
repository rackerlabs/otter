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
        super(OtterHistoryTestCase, self).setUp()
        set_config_data({'elasticsearch': {'host': "http://dummy/search"}})

    @mock.patch('otter.rest.history.treq')
    def test_history(self, treq):
        """
        the history api endpoint returns the items from the audit log
        """
        data = {'abc': 'def'}
        response = mock.Mock(content=json.dumps(data))

        def get(*args, **kwargs):
            return defer.succeed(response)
        treq.get.side_effect = get

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        body = self.assert_status_code(200)
        result = json.loads(body)
        self.assertEqual(result, data)
