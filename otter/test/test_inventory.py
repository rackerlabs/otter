"""
Tests for :mod:`otter.inventory`
"""
import json
import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web.client import Agent

from otter.test.utils import mock_agent_request, DeferredTestMixin
from otter import inventory


class AddToScalingGroupTestCase(DeferredTestMixin, TestCase):
    """
    Tests for :func:`otter.inventory.add_entity_to_scaling_group`
    """
    def setUp(self):
        # don't depend on config.INVENTORY_URL to be one particular thing
        self.url_patcher = mock.patch.object(inventory.config,
                                             'INVENTORY_URL',
                                             new="http://url.me")
        self.url_patcher.start()

        self.tenant_id = "11111"
        self.entity_id = "10"

        self.mock_agent = mock.MagicMock(spec=Agent)

    def tearDown(self):
        self.url_patcher.stop()

    def test_default_entity_type_values(self):
        """
        Default value for entity type is provided, and the correct method,
        body, and URL are used in the request.
        """
        request_call = defer.Deferred()
        self.mock_agent.request.side_effect = mock_agent_request(request_call)

        # ignore the output of request in this test
        throwout = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        throwout.addBoth(lambda _: None)

        url = "http://url.me/11111/servers/10/service_tags/{0}/".format(
            inventory.SCALING_GROUP_SERVICE_NAME)

        return request_call.addCallback(self.assertEqual, {
                'method': 'POST',
                'uri': url,
                'headers': None,
                'body': json.dumps(['atag'])
            })

    def test_provided_entity_type_value(self):
        """
        Provided value for entity type is used in the URL, and the correct
        method, body, and URL are used in the request.
        """
        request_call = defer.Deferred()
        self.mock_agent.request.side_effect = mock_agent_request(request_call)

        # ignore the output of request in this test
        throwout = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", entity_type="db",
            agent=self.mock_agent)
        throwout.addBoth(lambda _: None)

        url = "http://url.me/11111/db/10/service_tags/{0}/".format(
            inventory.SCALING_GROUP_SERVICE_NAME)

        return request_call.addCallback(self.assertEqual, {
                'method': 'POST',
                'uri': url,
                'headers': None,
                'body': json.dumps(['atag'])
            })

    def test_204_returns_none(self):
        """
        If the agent returns a 204,
        :func:`inventory.add_entity_to_scaling_group` will ultimately callback
        with None
        """
        self.mock_agent.request.return_value = defer.succeed(mock.MagicMock(
            spec=["code", "content"], code=204))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        self.assertEqual(None, self.assert_deferred_succeeded(deferred))

    def test_404_raises_InvalidEntityError(self):
        """
        If the agent returns a 404 "Not found",
        :func:`inventory.add_entity_to_scaling_group` will ultimately errback
        with an InvalidEntityError
        """
        self.mock_agent.request.return_value = defer.succeed(mock.MagicMock(
            spec=["code", "content"], code=404))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        self.assert_deferred_failed(deferred, inventory.InvalidEntityError)

    def test_not_200_or_204_or_404_raises_InventoryError(self):
        """
        If the agent not a 204, 200, or 404,
        :func:`inventory.add_entity_to_scaling_group` will ultimately errback
        with an InventoryError
        """
        self.mock_agent.request.return_value = defer.succeed(mock.MagicMock(
            spec=["code", "content"], code=404))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        self.assert_deferred_failed(deferred, inventory.InventoryError)
