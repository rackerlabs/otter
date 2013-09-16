"""
Tests for :mod:`otter.rest.limits`, which include the endpoints getting
group limits
"""

import json
from twisted.trial.unittest import TestCase

from otter.rest.application import Otter
from otter.test.rest.request import RestAPITestMixin, request
from otter.test.utils import iMock
from otter.models.interface import IScalingGroupCollection

class OtterLimitsTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/limits``
    """
    tenant_id = '11111'
    endpoint = "/v1.0/11111/limits"

    invalid_methods = ("DELETE", "PUT", "POST")

    def test_list_limits_json(self):
        data = {
            "limits": {
                "absolute": {
                    "maxGroups": 1000,
                    "maxPoliciesPerGroup": 1000,
                    "maxWebhooksPerPolicy": 1000,
                }
            }
        }
        body = self.assert_status_code(200)
        resp = json.loads(body)
        self.assertEqual(resp, data)


    def test_list_limits_xml(self):
        data = '''<?xml version='1.0' encoding='UTF-8'?>\n<limits xmlns="http://docs.openstack.org/common/api/v1.0"><absolute><limit name="maxGroups" value="1000"/><limit name="maxPoliciesPerGroup" value="1000"/><limit name="maxWebhooksPerPolicy" value="1000"/></absolute></limits>'''

        root = Otter(iMock(IScalingGroupCollection)).app.resource()
        headers = {"Accept": ["application/xml"]}

        response_wrapper = self.successResultOf(
            request(root, "GET", self.endpoint, headers=headers))

        self.assertEqual(response_wrapper.response.headers.getRawHeaders('Content-Type'),
                         ['application/xml'])
        self.assertEqual(response_wrapper.response.code, 200)
        self.assertEqual(response_wrapper.content, data)
