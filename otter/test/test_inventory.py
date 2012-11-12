"""
Tests for :mod:`otter.inventory`
"""
import json
import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from twisted.web.client import Agent

from otter.test.utils import (DeferredTestMixin, mock_agent_request,
                              mock_response)
from otter import inventory


class AddToScalingGroupTestCase(DeferredTestMixin, TestCase):
    """
    Tests for :func:`otter.inventory.add_entity_to_scaling_group`
    """
    def setUp(self):
        """
        Don't depend on config.INVENTORY_URL to be one particular thing
        """
        self.url_patcher = mock.patch.object(inventory.config,
                                             'INVENTORY_URL',
                                             new="http://url.me")
        self.url_patcher.start()

        self.tenant_id = "11111"
        self.entity_id = "10"

        self.mock_agent = mock.MagicMock(spec=Agent)

    def tearDown(self):
        """
        Undo patching
        """
        self.url_patcher.stop()

    def test_default_entity_type_values(self):
        """
        Default value for entity type is provided, and the correct method,
        body, and URL are used in the request.

        :return: Deferred that needs the reactor to spin in order to check
            equivalence
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

        :return: Deferred that needs the reactor to spin in order to check
            equivalence
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
        self.mock_agent.request.return_value = defer.succeed(
            mock_response(status_code=204))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        self.assertEqual(None, self.assert_deferred_succeeded(deferred))

    def test_404_raises_InvalidEntityError(self):
        """
        If the agent returns a 404 "Not found",
        :func:`inventory.add_entity_to_scaling_group` will ultimately errback
        with an InvalidEntityError
        """
        self.mock_agent.request.return_value = defer.succeed(mock_response(
            status_code=404))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)
        self.assert_deferred_failed(deferred, inventory.InvalidEntityError)

    def test_not_200_or_204_or_404_raises_InventoryError(self):
        """
        If the agent not a 204, 200, or 404,
        :func:`inventory.add_entity_to_scaling_group` will ultimately errback
        with an InventoryError
        """
        for code in (403, 500, 401):
            self.mock_agent.request.return_value = defer.succeed(
                mock_response(status_code=code))
            deferred = inventory.add_entity_to_scaling_group(
                self.tenant_id, self.entity_id, "atag", agent=self.mock_agent)

            self.assert_deferred_failed(deferred, inventory.InventoryError)

    @mock.patch('otter.inventory._agent', new=None)
    @mock.patch('twisted.internet.reactor')
    @mock.patch('otter.inventory.Agent', spec=Agent)
    def test_if_no_agent_passed_makes_agent(self, mock_agent, mock_reactor):
        """
        If no agent is provided, uses its own agent
        """
        request = mock_agent.return_value.request
        request.return_value = defer.succeed(mock_response(status_code=204))
        deferred = inventory.add_entity_to_scaling_group(
            self.tenant_id, self.entity_id, "atag")
        self.assert_deferred_succeeded(deferred)

        mock_agent.assert_called_once_with(mock_reactor)
        self.assertEqual(len(request.mock_calls), 1)


class GetInScalingGroupTestCase(DeferredTestMixin, TestCase):
    """
    Tests for :func:`otter.inventory.get_entities_in_scaling_group`
    """
    def setUp(self):
        """
        Don't depend on config.INVENTORY_URL to be one particular thing
        """
        self.url_patcher = mock.patch.object(inventory.config,
                                             'INVENTORY_URL',
                                             new="http://url.me")
        self.url_patcher.start()

        self.tenant_id = "11111"
        self.scaling_group = "10"

        self.mock_agent = mock.MagicMock(spec=Agent)

    def tearDown(self):
        """
        Undo patching
        """
        self.url_patcher.stop()

    def test_default_entity_type_values(self):
        """
        Default value for entity type is provided, and the correct method,
        body, and URL are used in the request.

        :return: Deferred that needs the reactor to spin in order to check
            equivalence
        """
        request_call = defer.Deferred()
        self.mock_agent.request.side_effect = mock_agent_request(request_call)

        # ignore the output of request in this test
        throwout = inventory.get_entities_in_scaling_group(
            self.tenant_id, self.scaling_group, agent=self.mock_agent)
        throwout.addBoth(lambda _: None)

        url = "http://url.me/11111/servers/service_tags/{0}/".format(
            inventory.SCALING_GROUP_SERVICE_NAME)

        return request_call.addCallback(self.assertEqual, {
            'method': 'GET',
            'uri': url,
            'headers': None,
            'body': ''
        })

    def test_provided_entity_type_value(self):
        """
        Provided value for entity type is used in the URL, and the correct
        method, body, and URL are used in the request.

        :return: Deferred that needs the reactor to spin in order to check
            equivalence
        """
        request_call = defer.Deferred()
        self.mock_agent.request.side_effect = mock_agent_request(request_call)

        # ignore the output of request in this test
        throwout = inventory.get_entities_in_scaling_group(
            self.tenant_id, self.scaling_group, entity_type="db",
            agent=self.mock_agent)
        throwout.addBoth(lambda _: None)

        url = "http://url.me/11111/db/service_tags/{0}/".format(
            inventory.SCALING_GROUP_SERVICE_NAME)

        return request_call.addCallback(self.assertEqual, {
            'method': 'GET',
            'uri': url,
            'headers': None,
            'body': ''
        })

    def test_200_with_existing_entities_returns_list_of_entities(self):
        """
        If the agent returns a 200, and there are entities in the results
        returned, :func:`inventory.get_entities_in_scaling_group` will
        ultimately callback with the list
        """
        self.mock_agent.request.return_value = defer.succeed(mock_response(
            body=json.dumps({"servers": {"10": ["stuff"]}})))
        deferred = inventory.get_entities_in_scaling_group(
            self.tenant_id, self.scaling_group, agent=self.mock_agent)
        self.assertEqual(["stuff"], self.assert_deferred_succeeded(deferred))

    def test_200_with_no_entities_returns_empty_list(self):
        """
        If the agent returns a 200, and there are no entties in the results
        returned, :func:`inventory.get_entities_in_scaling_group` will
        ultimately callback an empty list
        """
        self.mock_agent.request.return_value = defer.succeed(mock_response(
            body=json.dumps({"servers": {}})))
        deferred = inventory.get_entities_in_scaling_group(
            self.tenant_id, self.scaling_group, agent=self.mock_agent)
        self.assertEqual([], self.assert_deferred_succeeded(deferred))

    def test_non_204_or_200_raises_InventoryError(self):
        """
        If the agent returns not a 204 or 200,
        :func:`inventory.get_entities_in_scaling_group` will ultimately errback
        with an InventoryError
        """
        for code in (404, 403, 500):
            self.mock_agent.request.return_value = defer.succeed(
                mock_response(status_code=code))
            deferred = inventory.get_entities_in_scaling_group(
                self.tenant_id, self.scaling_group, agent=self.mock_agent)
            self.assert_deferred_failed(deferred, inventory.InventoryError)

    @mock.patch('otter.inventory._agent', new=None)
    @mock.patch('twisted.internet.reactor')
    @mock.patch('otter.inventory.Agent', spec=Agent)
    def test_if_no_agent_passed_makes_agent(self, mock_agent, mock_reactor):
        """
        If no agent is provided, uses its own agent
        """
        request = mock_agent.return_value.request
        request.return_value = defer.succeed(mock_response(status_code=500))
        deferred = inventory.get_entities_in_scaling_group(
            self.tenant_id, self.scaling_group)
        self.assert_deferred_failed(deferred)

        mock_agent.assert_called_once_with(mock_reactor)
        self.assertEqual(len(request.mock_calls), 1)
