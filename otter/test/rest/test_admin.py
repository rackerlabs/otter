"""
Tests for the OtterAdmin application.
"""
import json
import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.test.rest.request import AdminRestAPITestMixin


class AdminEndpointsTestCase(AdminRestAPITestMixin, TestCase):
    """
    Tests against the OtterAdmin endpoints.
    """
    endpoint = '/'

    def test_root_endpoint_exists(self):
        """
        Ensures the root endpoint exists, and has headers 'X-Request-ID'
        and 'content-type' set.
        """
        response_body = self.assert_status_code(200)
        self.assertEqual('', response_body)

    @mock.patch('otter.rest.admin.OtterMetrics')
    def test_metrics_endpoint_delegates(self, OtterMetrics):
        """
        '/metrics' should return the OtterMetrics resource, and an empty
        list of metrics.
        """
        self.endpoint = '/metrics'

        metrics = {'metrics': []}

        otter_app = OtterMetrics().app
        otter_app.resource.return_value = defer.succeed(json.dumps(metrics))

        response_body = json.loads(self.assert_status_code(200))
        self.assertEqual(metrics, response_body)

        OtterMetrics.assert_called_with(self.mock_store, mock.ANY)
