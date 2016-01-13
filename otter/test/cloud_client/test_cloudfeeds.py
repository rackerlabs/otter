"""Tests for otter.cloud_client.cloudfeeds"""

from twisted.trial.unittest import SynchronousTestCase

from effect import sync_perform
from effect.testing import EQFDispatcher

from otter.constants import ServiceType
from otter.cloud_client import service_request
from otter.cloud_client.cloudfeeds import publish_autoscale_event
from otter.test.cloud_client.test_init import service_request_eqf
from otter.test.utils import stub_pure_response
from otter.util.pure_http import APIError, has_code


class CloudFeedsTests(SynchronousTestCase):
    """
    Tests for cloud feed functions.
    """
    def test_publish_autoscale_event(self):
        """
        Publish an event to cloudfeeds.  Successfully handle non-JSON data.
        """
        _log = object()
        eff = publish_autoscale_event({'event': 'stuff'}, log=_log)
        expected = service_request(
            ServiceType.CLOUD_FEEDS, 'POST',
            'autoscale/events',
            headers={'content-type': ['application/vnd.rackspace.atom+json']},
            data={'event': 'stuff'}, log=_log, success_pred=has_code(201),
            json_response=False)

        # success
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('<this is xml>', 201)))])
        resp, body = sync_perform(dispatcher, eff)
        self.assertEqual(body, '<this is xml>')

        # Add regression test that 202 should be an API error because this
        # is a bug in CF
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('<this is xml>', 202)))])
        self.assertRaises(APIError, sync_perform, dispatcher, eff)

