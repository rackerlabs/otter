"""
Tests for `otter.rest.history`
"""
import json

import mock
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web.client import Agent

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

    @mock.patch('otter.rest.history.Agent')
    def test_history(self, _Agent):
        """
        the history api endpoint returns the items from the audit log
        """
        data = {'abc': 'def'}
        agent = mock.create_autospec(Agent)

        def _request(*args, **kwargs):
            return defer.succeed(json.dumps(data))
        agent.request.side_effect = _request
        _Agent.return_value = agent

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        body = self.assert_status_code(200)
        result = json.loads(body)
        self.assertEqual(result, data)
