"""
"""
import mock

from twisted.trial.unittest import TestCase

from otter.test.rest.request import RequestTestMixin

from otter.rest.admin import OtterAdmin


class OtterAdminTestCase(RequestTestMixin, TestCase):
    """
    """

    def __init__(self, *args, **kwargs):
        oa = OtterAdmin()
        self.root = oa.app.resource()

        super(OtterAdminTestCase, self).__init__(*args, **kwargs)

    def test_root_endpoint_empty(self):
        """
        Sanity test to ensure root endpoint exists and contains no data.
        """
        self.endpoint = '/'

        request_body = self.assert_status_code(200)
        self.assertEqual('', request_body)

    def test_metrics_endpoint_contains_metrics_string(self):
        """
        '/metrics' should contains 'metrics'
        """
        self.endpoint = '/metrics'

        request_body = self.assert_status_code(200)
        self.assertIn('metrics', request_body)
