"""
Tests for `otter.rest.history`
"""
import json

from twisted.trial.unittest import TestCase

from testtools.matchers import IsInstance

from otter.test.rest.request import RestAPITestMixin, request
from otter.util.config import set_config_data
from otter.test.utils import mock_log, patch, mock_treq, matches


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
        set_config_data({
            'elasticsearch': {'host': 'http://dummy'},
            'limits': {'pagination': 20}})
        self.addCleanup(lambda: set_config_data({}))

        self.log = patch(self, 'otter.rest.history.log', new=mock_log())
        self.make_auditlog_query = patch(
            self, 'otter.rest.history.make_auditlog_query',
            return_value={'tenant_id': 101010})

        self.treq = patch(self, 'otter.rest.history.treq', new=mock_treq(
            code=200, method='get', json_content={'hits': {
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
            ))

    def test_history(self):
        """
        the history api endpoint returns the items from the audit log
        """
        expected = {
            'events': [{
                'event_type': 'event-abc',
                'timestamp': 1234567890,
                'policy_id': 'policy-xyz',
                'scaling_group_id': 'scaling-group-uvw',
                'server_id': 'server-rst',
                'message': 'audit log event',
            }],
            'events_links': [{'href': '/v1.0/101010/history', 'rel': 'self'}]
        }

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        self.treq.get.assert_called_once_with(
            'http://dummy/_search', data='{"tenant_id": 101010}',
            log=matches(IsInstance(self.log.__class__)))
        self.assertTrue(self.treq.json_content.called)

        self.make_auditlog_query.assert_called_once_with('101010', None, limit=20)

    def test_history_with_pagination(self):
        """
        The history api endpoint returns the items from the audit log, and
        paginates them if there are more than the limit
        """
        expected = {
            'events': [{
                'event_type': 'event-abc',
                'timestamp': 1234567890,
                'policy_id': 'policy-xyz',
                'scaling_group_id': 'scaling-group-uvw',
                'server_id': 'server-rst',
                'message': 'audit log event',
            }],
            'events_links': [{'href': '/v1.0/101010/history?marker=10&limit=1', 'rel': 'self'},
                             {'href': '/v1.0/101010/history?marker=11&limit=1', 'rel': 'next'}]
        }

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint + "?marker=10&limit=1"))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        self.treq.get.assert_called_once_with(
            'http://dummy/_search', data='{"tenant_id": 101010}',
            log=matches(IsInstance(self.log.__class__)))
        self.assertTrue(self.treq.json_content.called)

        self.make_auditlog_query.assert_called_once_with('101010', None, marker='10', limit=1)
