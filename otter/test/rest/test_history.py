"""
Tests for `otter.rest.history`
"""
import json

from twisted.trial.unittest import TestCase

from testtools.matchers import IsInstance

from otter.test.rest.request import RestAPITestMixin, request
from otter.util.config import set_config_data
from otter.test.utils import mock_log, patch, mock_treq, matches

from otter.rest.history import make_auditlog_query


class MakeAuditLogQueryTestCase(TestCase):
    """
    Tests for ``make_auditlog_query``
    """
    def test_filters_by_tenant_id(self):
        """
        The filtered query includes the tenant id
        """
        results = make_auditlog_query("MY_TENANT_ID   ", "region", 0, 1)
        self.assertIn('"tenant_id": "MY_TENANT_ID"', json.dumps(results))

    def test_filters_by_region(self):
        """
        The filtered query includes the normalized region
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 0, 1)
        self.assertIn('"tags": "dfw"', json.dumps(results))

    def test_limits_size_of_results(self):
        """
        The filtered query sets 'size' as the limit passed to it
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 0, 100)
        self.assertEqual(results['size'], 100)

    def test_sets_offset_to_marker(self):
        """
        The filtered query sets 'from' as the marker offset passed to it
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 5, 100)
        self.assertEqual(results['from'], 5)

    def test_queries_in_reverse_chronological_order(self):
        """
        The filtered query sorts by reverse chronological order
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 5, 100)
        self.assertEqual(results['sort'], [{"@timestamp": {"order": "desc"}}])


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
            'limits': {'pagination': 20},
            'url_root': 'http://localhost'})

        self.addCleanup(set_config_data, {})

        self.log = patch(self, 'otter.rest.history.log', new=mock_log())
        self.make_auditlog_query = patch(
            self, 'otter.rest.history.make_auditlog_query',
            return_value={'tenant_id': 101010})

        self.treq = patch(self, 'otter.rest.history.treq', new=mock_treq(
            code=200, method='get', json_content={
                'hits': {
                    'hits': [{
                        '_source': {
                            'message': 'audit log event',
                            'event_type': 'event-abc',
                            '@timestamp': 1234567890,
                            'policy_id': 'policy-xyz',
                            'scaling_group_id': 'scaling-group-uvw',
                            'server_id': 'server-rst',
                            'throwaway_key': 'ignore me!!!!'
                        }
                    }]
                }
            }))

    def test_history_not_implemented_if_not_configured(self):
        """
        A 501 not implemented error is returned if there is no configured host
        """
        set_config_data({
            'limits': {'pagination': 20},
            'url_root': 'http://localhost'})
        self.assert_status_code(501)


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
            'events_links': [{'href': 'http://localhost/v1.0/101010/history', 'rel': 'self'}]
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
            'events_links': [
                {'href': 'http://localhost/v1.0/101010/history?limit=1&marker=10', 'rel': 'self'},
                {'href': 'http://localhost/v1.0/101010/history?limit=1&marker=11', 'rel': 'next'}]
        }

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint + "?limit=1&marker=10"))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        self.treq.get.assert_called_once_with(
            'http://dummy/_search', data='{"tenant_id": 101010}',
            log=matches(IsInstance(self.log.__class__)))
        self.assertTrue(self.treq.json_content.called)

        self.make_auditlog_query.assert_called_once_with('101010', None, marker='10', limit=1)
