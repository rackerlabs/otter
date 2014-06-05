"""
Tests for the OtterAdmin application.
"""
import json

from twisted.internet import defer
from twisted.trial.unittest import SynchronousTestCase

from otter.test.rest.request import AdminRestAPITestMixin


class AdminEndpointsTestCase(AdminRestAPITestMixin, SynchronousTestCase):
    """
    Tests against the OtterAdmin endpoints.
    """
    def test_metrics_endpoint_delegates(self):
        """
        '/metrics' should return the OtterMetrics resource, and an empty
        list of metrics.
        """
        self.endpoint = '/metrics'

        metrics = {'metrics': []}

        self.mock_store.get_metrics.return_value = defer.succeed([])

        response_body = json.loads(self.assert_status_code(200))
        self.assertEqual(metrics, response_body)
