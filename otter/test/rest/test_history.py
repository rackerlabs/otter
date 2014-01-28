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
        set_config_data({'elasticsearch': {'host': "http://dummy"}})

    @mock.patch('otter.rest.history.log')
    @mock.patch('otter.rest.history.make_auditlog_query')
    @mock.patch('otter.rest.history.treq')
    def test_history(self, treq, make_auditlog_query, log):
        """
        the history api endpoint returns the items from the audit log
        """
        log_object = mock.Mock()

        def return_log_object(*args, **kwargs):
            return log_object
        log.bind.side_effect = return_log_object

        data = {'hits': {
            'hits': [{
                '_source': {
                    'message': 'audit log event',
                    'event_type': 'event-abc',
                    '@timestamp': 1234567890,
                    'policy_id': 'policy-xyz',
                    'scaling_group_id': 'scaling-group-uvw',
                    'server_id': 'server-rst',
                }
                }]}}
        expected = {
            'events': [{
                'event_type': 'event-abc',
                'timestamp': 1234567890,
                'policy_id': 'policy-xyz',
                'scaling_group_id': 'scaling-group-uvw',
                'server_id': 'server-rst',
                'message': 'audit log event',
            }]
        }
        make_auditlog_query.return_value = {'tenant_id': 101010}
        response = mock.Mock(code=200)

        def get(*args, **kwargs):
            return defer.succeed(response)
        treq.get.side_effect = get

        def json_content(*args, **kwargs):
            return defer.succeed(data)
        treq.json_content.side_effect = json_content

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        treq.get.assert_called_once_with(
            'http://dummy/_search', '{"tenant_id": 101010}', log=log_object.bind())
        treq.json_content.assert_called_once_with(response)
