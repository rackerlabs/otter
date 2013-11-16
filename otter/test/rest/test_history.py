"""
Tests for `otter.rest.history`
"""
import json

from twisted.trial.unittest import TestCase

from otter.test.rest.request import RestAPITestMixin, request


class OtterHistoryTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/history``
    """
    tenant_id = '101010'
    endpoint = '/v1.0/101010/history'

    invalid_methods = ("DELETE", "PUT", "POST")

    def test_history(self):
        """
        the history api endpoint returns the items from the audit log
        """
        data = {}

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint))

        body = self.assert_status_code(200)
        result = json.loads(body)
        self.assertEqual(result, data)

    def test_history_xml(self):
        """
        the history api endpoint can return xml when requested
        """
        headers = {"Accept": ["application/xml"]}

        result = self.successResultOf(
            request(self.root, "GET", self.endpoint, headers=headers))

        self.assertEqual(result.response.headers.getRawHeaders('Content-Type'),
                         ['application/xml'])
        self.assertEqual(result.response.code, 200)
