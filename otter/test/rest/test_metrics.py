"""
Tests for the OtterMetrics application.
"""
import json
import mock

from twisted.internet import defer
from twisted.trial.unittest import SynchronousTestCase

from otter.test.rest.request import AdminRestAPITestMixin


class MetricsEndpointsTestCase(AdminRestAPITestMixin, SynchronousTestCase):
    """
    Tests for '/metrics' endpoint, which contains metrics regarding the
    Otter system as a whole.
    """
    endpoint = '/metrics'

    def test_metrics_endpoint_contains_metrics_string(self):
        """
        Requests for metrics returns a json payload of all available metrics.
        """
        metrics = [
            {
                'id': 'otter.metrics.foo',
                'value': 10,
                'time': '1234567890'
            },
            {
                'id': 'otter.metrics.bar',
                'value': 42,
                'time': '2345678901'
            }
        ]

        self.mock_store.get_metrics.return_value = defer.succeed(metrics)

        response_body = json.loads(self.assert_status_code(200))
        self.assertEqual(response_body, {'metrics': metrics})

        self.mock_store.get_metrics.assert_called_once_with(mock.ANY)
