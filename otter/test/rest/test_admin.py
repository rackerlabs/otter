"""
Tests related to the OtterAdmin application
"""

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.rest.admin import OtterAdmin
from otter.test.rest.request import RestAPITestMixin
from otter.test.utils import iMock, patch
from otter.models.interface import IAdmin


class AdminMetricsAPITestCase(RestAPITestMixin, TestCase):
    """
    Tests against the metrics endpoint of OtterAdmin.
    """

    invalid_methods = ['PUT', 'POST', 'DELETE']
    endpoint = '/metrics'

    def setUp(self):
        """
        Overrides RestAPITestMixin.setUp

         * Sets up a mock store that conforms to IAdmin
         * Patches 'generate_transaction_id' in decorators
         * Changes the root app to be OtterAdmin
        """
        self.mock_store = iMock(IAdmin)

        self.mock_generate_transaction_id = patch(
            self, 'otter.rest.decorators.generate_transaction_id',
            return_value='transaction-id')

        self.root = OtterAdmin(self.mock_store).app.resource()

    def test_metrics_endpoint_exists(self):
        """
        Ensure the 'metrics' endpoint is reachable.
        """
        self.mock_store.get_metrics.return_value = defer.succeed({})
        self.assert_status_code(200)
