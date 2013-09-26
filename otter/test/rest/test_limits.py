"""
Tests for :mod:`otter.rest.limits`, which include the endpoints getting
group limits
"""

import json
from twisted.trial.unittest import TestCase

from otter.test.rest.request import RestAPITestMixin, request
from otter.util.config import set_config_data

number = 2


class OtterLimitsTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/limits``
    """
    tenant_id = '11111'
    endpoint = "/v1.0/11111/limits"

    invalid_methods = ("DELETE", "PUT", "POST")

    def setUp(self):
        """
        setup fake config data
        """
        self.limits = ["maxGroups", "maxPoliciesPerGroup", "maxWebhooksPerPolicy"]
        data = {
            "limits": {
                "pagination": 500,
                "absolute": {limit: number for limit in self.limits}
            }
        }

        super(OtterLimitsTestCase, self).setUp()
        set_config_data(data)

    def tearDown(self):
        """
        remove fake config data
        """
        super(OtterLimitsTestCase, self).tearDown()
        set_config_data({})

    def test_list_limits_json(self):
        """
        the api returns a json blob containing the absolute
        limits in the correct format, and ignores other limits in the config.
        """
        data = {"limits": {"absolute": {limit: number for limit in self.limits}}}
        body = self.assert_status_code(200)
        resp = json.loads(body)
        self.assertEqual(resp, data)

    def test_list_limits_xml(self):
        """
        the api returns a xml blob containing the absolute
        limits in the correct format, if the "Accept" header
        specifies xml
        """
        data = ("<?xml version='1.0' encoding='UTF-8'?>\n"
                '<limits xmlns="http://docs.openstack.org/common/api/v1.0">'
                '<absolute>'
                '<limit name="maxGroups" value="{0}"/>'
                '<limit name="maxPoliciesPerGroup" value="{0}"/>'
                '<limit name="maxWebhooksPerPolicy" value="{0}"/>'
                '</absolute></limits>')

        data = data.format(number)
        headers = {"Accept": ["application/xml"]}

        response_wrapper = self.successResultOf(
            request(self.root, "GET", self.endpoint, headers=headers))

        self.assertEqual(response_wrapper.response.headers.getRawHeaders('Content-Type'),
                         ['application/xml'])
        self.assertEqual(response_wrapper.response.code, 200)
        self.assertEqual(response_wrapper.content, data)
