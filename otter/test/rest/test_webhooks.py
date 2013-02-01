"""
Tests for :mod:`otter.rest.webhooks`, which include the endpoints for listing
webhooks, and creating/viewing/deleting webhooks.
"""

import json
from jsonschema import validate, ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.json_schema import rest_schemas
from otter.models.interface import (
    NoSuchScalingGroupError, NoSuchPolicyError, NoSuchWebhookError)
from otter.rest.decorators import InvalidJsonError
from otter.test.rest.request import DummyException, RestAPITestMixin


class WebhookCollectionTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks``
    endpoints (create, list)
    """
    tenant_id = '11111'
    group_id = '1'
    policy_id = '2'
    endpoint = "/v1.0/11111/groups/1/policies/2/webhooks"

    invalid_methods = ("DELETE", "PUT")

    def test_list_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.list_webhooks.return_value = defer.fail(error)
        self.assert_status_code(500)
        self.mock_group.list_webhooks.assert_called_once_with(self.policy_id)
        self.flushLoggedErrors(DummyException)

    def test_list_webhooks_for_unknowns_is_404(self):
        """
        When listing webhooks, endpoint returns 404 if:
        - the group doesn't exist, :class:`NoSuchScalingGroupError` is raised
        - the policy doesn't exist, :class:`NoSuchPolicyError` is raised
        """
        errors = [
            NoSuchScalingGroupError(self.tenant_id, self.group_id),
            NoSuchPolicyError(self.tenant_id, self.group_id, self.policy_id)]
        for error in errors:
            self.mock_group.list_webhooks.return_value = defer.fail(error)
            self.assert_status_code(404)
            self.mock_group.list_webhooks.assert_called_once_with(self.policy_id)
            self.flushLoggedErrors(type(error))
            self.mock_group.list_webhooks.reset_mock()

    def test_no_webhooks_returns_empty_list(self):
        """
        If there are no groups for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        self.mock_group.list_webhooks.return_value = defer.succeed({})
        body = self.assert_status_code(200)
        self.mock_group.list_webhooks.assert_called_once_with(self.policy_id)

        resp = json.loads(body)
        self.assertEqual(resp, {"webhooks": [], "webhooks_links": []})
        validate(resp, rest_schemas.list_webhooks_response)

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_returned_webhooks_dict_gets_translated(self, mock_url):
        """
        Test that the webhooks dict gets translated into a list of webhooks
        with ids and links.
        """
        # return two webhook objects
        self.mock_group.list_webhooks.return_value = defer.succeed({
            "3": {'name': 'three', 'metadata': {},
                  'capability': {'hash': 'xxx', 'version': '1'}},
            "4": {'name': 'four', 'metadata': {},
                  'capability': {'hash': 'yyy', 'version': '1'}}
        })
        body = self.assert_status_code(200)
        self.mock_group.list_webhooks.assert_called_once_with(self.policy_id)

        resp = json.loads(body)
        validate(resp, rest_schemas.list_webhooks_response)
        self.assertEqual(resp, {
            "webhooks": [
                {
                    'id': '3',
                    'name': 'three',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/3',
                         "rel": "self"},
                        {"href": '/11111/groups/1/policies/2/webhooks/3',
                         "rel": "bookmark"},
                        {"href": '/v1.0/execute/1/xxx', "rel": "capability"}
                    ]
                },
                {
                    'id': '4',
                    'name': 'four',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/4',
                         "rel": "self"},
                        {"href": '/11111/groups/1/policies/2/webhooks/4',
                         "rel": "bookmark"},
                        {"href": '/v1.0/execute/1/yyy', "rel": "capability"}
                    ]
                }
            ],
            "webhooks_links": []
        })

    def test_create_webhooks_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.create_webhooks.return_value = defer.fail(error)
        self.assert_status_code(500, None, 'POST', json.dumps(
                                [{'name': 'one'}]))
        self.mock_group.create_webhooks.assert_called_once_with(
            self.policy_id, [{'name': 'one'}])
        self.flushLoggedErrors(DummyException)

    def test_create_webhooks_for_unknowns_is_404(self):
        """
        When listing webhooks, endpoint returns 404 if:
        - the group doesn't exist, :class:`NoSuchScalingGroupError` is raised
        - the policy doesn't exist, :class:`NoSuchPolicyError` is raised
        """
        errors = [
            NoSuchScalingGroupError(self.tenant_id, self.group_id),
            NoSuchPolicyError(self.tenant_id, self.group_id, self.policy_id)]
        for error in errors:
            self.mock_group.list_webhooks.return_value = defer.fail(error)
            self.assert_status_code(404, None, 'POST', json.dumps(
                                    [{'name': 'one'}]))
            self.mock_group.create_webhooks.assert_called_once_with(
                self.policy_id, [{'name': 'one'}])
            self.flushLoggedErrors(type(error))
            self.mock_group.create_webhooks.reset_mock()

    def test_create_webhooks_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_group.create_webhooks.return_value = defer.succeed({})
        self.assert_status_code(400, None, 'POST', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_create_webhooks_invalid_schema_400(self):
        """
        Checks that the webhooks is obeyed - an empty schema is bad.
        """
        self.mock_group.create_webhooks.return_value = defer.succeed({})
        response_body = self.assert_status_code(400, None, 'POST', '[]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_webhooks_create(self, mock_url):
        """
        Tries to create a set of webhooks.
        """
        creation = [{'name': 'three'}, {'name': 'four'}]
        self.mock_group.create_webhooks.return_value = defer.succeed({
            "3": {'name': 'three', 'metadata': {},
                  'capability': {'hash': 'xxx', 'version': '1'}},
            "4": {'name': 'four', 'metadata': {},
                  'capability': {'hash': 'yyy', 'version': '1'}}
        })
        response_body = self.assert_status_code(
            201, None, 'POST', json.dumps(creation),
            # location header points to the webhooks list
            '/v1.0/11111/groups/1/policies/2/webhooks')

        self.mock_group.create_webhooks.assert_called_once_with(
            self.policy_id, creation)

        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_webhooks_response)

        self.assertEqual(resp, {
            "webhooks": [
                {
                    'id': '3',
                    'name': 'three',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/3',
                         "rel": "self"},
                        {"href": '/11111/groups/1/policies/2/webhooks/3',
                         "rel": "bookmark"},
                        {"href": '/v1.0/execute/1/xxx', "rel": "capability"}
                    ]
                },
                {
                    'id': '4',
                    'name': 'four',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/4',
                         "rel": "self"},
                        {"href": '/11111/groups/1/policies/2/webhooks/4',
                         "rel": "bookmark"},
                        {"href": '/v1.0/execute/1/yyy', "rel": "capability"}
                    ]
                }
            ]
        })


class WebhookCollectionTestCase(RestAPITestMixin, TestCase):
    """
    Tests for
    ``/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks/{webhookId}``
    endpoints (get, update, delete)
    """
    tenant_id = '11111'
    group_id = '1'
    policy_id = '2'
    webhook_id = '3'
    endpoint = "/v1.0/11111/groups/1/policies/2/webhooks/3"

    invalid_methods = ("POST")

    def test_update_webhook_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.update_webhook.return_value = defer.fail(error)
        self.assert_status_code(500, None, 'PUT', json.dumps(
                                {'name': 'one'}))
        self.mock_group.update_webhook.assert_called_once_with(
            self.policy_id, self.webhook_id, {'name': 'one'})
        self.flushLoggedErrors(DummyException)

    def test_update_webhook_for_unknowns_is_404(self):
        """
        When updating a webhook, endpoint returns a 404 if:
        - the group doesn't exist and :class:`NoSuchScalingGroupError` is raised
        - the policy doesn't exist and :class:`NoSuchPolicyError` is raised
        - the webhook doesn't exist and :class:`NoSuchWebhookError` is raised
        """
        errors = [
            NoSuchScalingGroupError(self.tenant_id, self.group_id),
            NoSuchPolicyError(self.tenant_id, self.group_id, self.policy_id),
            NoSuchWebhookError(self.tenant_id, self.group_id, self.policy_id,
                               self.webhook_id)]
        for error in errors:
            self.mock_group.update_webhook.return_value = defer.fail(error)
            self.assert_status_code(404, None, 'PUT', json.dumps(
                                    {'name': 'one'}))
            self.mock_group.update_webhook.assert_called_once_with(
                self.policy_id, self.webhook_id, {'name': 'one'})
            self.flushLoggedErrors(type(error))
            self.mock_group.update_webhook.reset_mock()

    def test_update_webhook_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        self.assert_status_code(400, None, 'PUT', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_update_webhook_invalid_schema_400(self):
        """
        Checks that the webhook schema is obeyed - an empty schema is bad.
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        response_body = self.assert_status_code(400, None, 'PUT', '[]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    def test_update_valid_webhook(self):
        """
        Checks that the update webhook returns an empty 204 if successful
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        response_body = self.assert_status_code(
            204, None, 'PUT', json.dumps({'name': 'a name'}))
        self.assertEqual(response_body, "")
