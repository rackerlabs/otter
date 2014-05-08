"""
Tests for `otter.rest.history`
"""
import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed

from testtools.matchers import IsInstance

from otter.test.rest.request import RestAPITestMixin, request
from otter.util.config import set_config_data
from otter.test.utils import mock_log, patch, mock_treq, matches

from otter.rest.history import make_auditlog_query, next_marker_by_timestamp


class MakeAuditLogQueryTestCase(SynchronousTestCase):
    """
    Tests for ``make_auditlog_query``
    """
    def assert_in_query(self, must_part, full_query):
        """
        Validates the form of the 'query' part of the query, and that
        `must_part` is in the correct part of the full query.
        """
        self.assertEqual(
            full_query['query'],
            {'filtered': {'filter': {'bool': {
                'must': matches(IsInstance(list))
            }}}}
        )
        self.assertIn(must_part,
                      full_query["query"]["filtered"]["filter"]["bool"]["must"])

    def test_filters_by_tenant_id(self):
        """
        The filtered query includes the tenant id
        """
        results = make_auditlog_query("MY_TENANT_ID   ", "region", 1)
        self.assert_in_query({'term': {'tenant_id': "MY_TENANT_ID"}}, results)

    def test_filters_by_region(self):
        """
        The filtered query includes the normalized region
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 1)
        self.assert_in_query({"term": {"tags": "dfw"}}, results)

    def test_limits_size_of_results(self):
        """
        The audit log query's ``size`` parameter is the limit passed to
        :func:`make_audit_log_query`
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", limit=100)
        self.assertEquals(results['size'], 100)

    def test_sets_range_query_to_last_30_days_if_no_marker(self):
        """
        If no marker is provided, the default range is 30 days ago until now
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 1)
        range_query = {
            "range": {
                "@timestamp": {
                    "from": "now-30d",
                    "to": "now"
                }
            }
        }
        self.assert_in_query(range_query, results)

    def test_sets_range_query_to_be_until_marker(self):
        """
        If marker is is provided, date range is 30 days ago until the marker
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 1,
                                      marker="new_date")
        range_query = {
            "range": {
                "@timestamp": {
                    "from": "now-30d",
                    "to": "new_date"
                }
            }
        }
        self.assert_in_query(range_query, results)

    def test_queries_in_reverse_chronological_order(self):
        """
        The filtered query sorts by reverse chronological order
        """
        results = make_auditlog_query("MY_TENANT_ID", "dFW", 1)
        self.assertEquals(results["sort"], [{"@timestamp": {'order': 'desc'}}])


class NextMarkerByTimestampTestCase(SynchronousTestCase):
    """
    ``next_marker_by_timestamp`` tests
    """
    def test_marker_by_timestamp_returns_last_timestamp(self):
        """
        ``next_marker_by_timestamp`` always returns the last item in the
        collection's timestamp
        """
        next_marker = next_marker_by_timestamp(
            [{'timestamp': 1}, {'timestamp': 2}], 2, 'ignore me')
        self.assertEqual(next_marker, 2)

    def test_marker_by_timestamp_correctly_limits_collection_size(self):
        """
        If the collection passed to ``next_marker_by_timestamp`` is too large,
        returns the timestamp of the limit-1'th element.
        """
        next_marker = next_marker_by_timestamp(
            [{'timestamp': 1}, {'timestamp': 2}], 1, 'ignore me')
        self.assertEqual(next_marker, 1)


class OtterHistoryTestCase(RestAPITestMixin, SynchronousTestCase):
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
        A 501 not implemented error is returned if there is no configured
        elasticsearch host
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

    def test_history_with_one_page_pagination(self):
        """
        The history api endpoint returns the items from the audit log, and
        paginates them if there are ``limit`` items in the collection, with the
        marker being the last timestamp
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
                {'href': 'http://localhost/v1.0/101010/history?limit=1',
                 'rel': 'self'},
                {'href': 'http://localhost/v1.0/101010/history?limit=1&marker=1234567890',
                 'rel': 'next'}]
        }

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint + "?limit=1"))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        self.treq.get.assert_called_once_with(
            'http://dummy/_search', data='{"tenant_id": 101010}',
            log=matches(IsInstance(self.log.__class__)))
        self.assertTrue(self.treq.json_content.called)

        self.make_auditlog_query.assert_called_once_with('101010', None, limit=1)

    def test_history_with_one_multi_page_pagination(self):
        """
        The history api endpoint returns the items from the audit log, and
        paginates them if there are more than ``limit`` items in the collection,
        with the marker being the timestamp of the ``limit-1``th item.
        """
        self.treq.json_content.return_value = succeed({
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'message': 'audit log event',
                            'event_type': 'event-abc',
                            '@timestamp': 1234567890,
                            'policy_id': 'policy-xyz',
                            'scaling_group_id': 'scaling-group-uvw',
                            'server_id': 'server-rst',
                            'throwaway_key': 'ignore me!!!!'
                        }
                    },
                    {
                        '_source': {
                            'message': 'audit log event 2',
                            'event_type': 'event-def',
                            '@timestamp': 1234567891,
                            'policy_id': 'policy-xyz',
                            'scaling_group_id': 'scaling-group-uvw',
                            'server_id': 'server-rst',
                            'throwaway_key': 'ignore me!!!!'
                        }
                    }
                ]
            }
        })

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
                {'href': 'http://localhost/v1.0/101010/history?limit=1',
                 'rel': 'self'},
                {'href': 'http://localhost/v1.0/101010/history?limit=1&marker=1234567890',
                 'rel': 'next'}]
        }

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint + "?limit=1"))

        self.assertEqual(200, result.response.code)
        self.assertEqual(expected, json.loads(result.content))

        self.treq.get.assert_called_once_with(
            'http://dummy/_search', data='{"tenant_id": 101010}',
            log=matches(IsInstance(self.log.__class__)))
        self.assertTrue(self.treq.json_content.called)

        self.make_auditlog_query.assert_called_once_with('101010', None, limit=1)
