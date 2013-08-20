"""
Tests for :mod:`otter.rest.webhooks`, which include the endpoints for listing
webhooks, and creating/viewing/deleting webhooks.
"""

import json
from jsonschema import ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.json_schema import rest_schemas, validate
from otter.models.interface import (
    NoSuchScalingGroupError, NoSuchPolicyError, NoSuchWebhookError,
    UnrecognizedCapabilityError)
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin

from otter.controller import CannotExecutePolicyError


class WebhookCollectionTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks``
    endpoints (create, list)
    """
    tenant_id = '11111'
    group_id = '1'
    policy_id = '2'
    endpoint = "/v1.0/11111/groups/1/policies/2/webhooks/"

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
            self.mock_group.list_webhooks.assert_called_once_with(
                self.policy_id)
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
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/3/',
                         "rel": "self"},
                        {"href": '/v1.0/execute/1/xxx/', "rel": "capability"}
                    ]
                },
                {
                    'id': '4',
                    'name': 'four',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/4/',
                         "rel": "self"},
                        {"href": '/v1.0/execute/1/yyy/', "rel": "capability"}
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
            self.mock_group.create_webhooks.return_value = defer.fail(error)
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
            '/v1.0/11111/groups/1/policies/2/webhooks/')

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
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/3/',
                         "rel": "self"},
                        {"href": '/v1.0/execute/1/xxx/', "rel": "capability"}
                    ]
                },
                {
                    'id': '4',
                    'name': 'four',
                    'metadata': {},
                    'links': [
                        {"href": '/v1.0/11111/groups/1/policies/2/webhooks/4/',
                         "rel": "self"},
                        {"href": '/v1.0/execute/1/yyy/', "rel": "capability"}
                    ]
                }
            ]
        })


class OneWebhookTestCase(RestAPITestMixin, TestCase):
    """
    Tests for
    ``/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks/{webhookId}``
    endpoints (get, update, delete)
    """
    tenant_id = '11111'
    group_id = '1'
    policy_id = '2'
    webhook_id = '3'
    endpoint = "/v1.0/11111/groups/1/policies/2/webhooks/3/"

    invalid_methods = ("POST")

    def setUp(self):
        """
        Set up webhook specific mocks.
        """
        super(OneWebhookTestCase, self).setUp()

        controller_patcher = mock.patch('otter.rest.webhooks.controller')
        self.mock_controller = controller_patcher.start()
        self.addCleanup(controller_patcher.stop)

        self.mock_group.uuid = self.group_id

    def test_get_webhook_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.get_webhook.return_value = defer.fail(error)
        self.assert_status_code(500)
        self.mock_group.get_webhook.assert_called_once_with(self.policy_id,
                                                            self.webhook_id)
        self.flushLoggedErrors(DummyException)

    def test_get_webhook_for_unknowns_is_404(self):
        """
        When getting a webhook, endpoint returns a 404 if:
        - the group doesn't exist and :class:`NoSuchScalingGroupError`
        is raised
        - the policy doesn't exist and :class:`NoSuchPolicyError` is raised
        - the webhook doesn't exist and :class:`NoSuchWebhookError` is raised
        """
        errors = [
            NoSuchScalingGroupError(self.tenant_id, self.group_id),
            NoSuchPolicyError(self.tenant_id, self.group_id, self.policy_id),
            NoSuchWebhookError(self.tenant_id, self.group_id, self.policy_id,
                               self.webhook_id)]
        for error in errors:
            self.mock_group.get_webhook.return_value = defer.fail(error)
            self.assert_status_code(404)
            self.mock_group.get_webhook.assert_called_once_with(
                self.policy_id,
                self.webhook_id)
            self.flushLoggedErrors(type(error))
            self.mock_group.get_webhook.reset_mock()

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_get_webhook(self, mock_url):
        """
        Get webhook returns a 200 with a body with the right schema if
        successful
        """
        self.mock_group.get_webhook.return_value = defer.succeed({
            'name': 'the_name',
            'capability': {
                'hash': 'xxx',
                'version': 'ver'
            },
            'metadata': {
                'key': 'value'
            }
        })
        response_body = self.assert_status_code(200)
        response = json.loads(response_body)
        validate(response, rest_schemas.view_webhook_response)
        self.assertEqual(response, {
            'webhook': {
                'name': 'the_name',
                'metadata': {
                    'key': 'value'
                },
                'id': self.webhook_id,
                'links': [
                    {
                        'rel': 'self',
                        'href': (
                            '/v1.0/{t}/groups/{g}/policies/{p}/webhooks/{w}/'
                            .format(t=self.tenant_id, g=self.group_id,
                                    p=self.policy_id, w=self.webhook_id))
                    },
                    {
                        'rel': 'capability',
                        'href': '/v1.0/execute/ver/xxx/'
                    }
                ]
            }
        })

    def test_update_webhook_missing_metadata_is_400(self):
        """
        A PUT with a valid JSON but no metadata returns a 400.
        """
        self.assert_status_code(400, None, 'PUT',
                                json.dumps({'name': 'hello'}))

    def test_update_webhook_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.update_webhook.return_value = defer.fail(error)
        self.assert_status_code(500, None, 'PUT', json.dumps(
                                {'name': 'one', 'metadata': {}}))
        self.mock_group.update_webhook.assert_called_once_with(
            self.policy_id, self.webhook_id, {'name': 'one', 'metadata': {}})
        self.flushLoggedErrors(DummyException)

    def test_update_webhook_for_unknowns_is_404(self):
        """
        When updating a webhook, endpoint returns a 404 if:
        - the group doesn't exist and :class:`NoSuchScalingGroupError`
        is raised
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
                                    {'name': 'one', 'metadata': {}}))
            self.mock_group.update_webhook.assert_called_once_with(
                self.policy_id, self.webhook_id,
                {'name': 'one', 'metadata': {}})
            self.flushLoggedErrors(type(error))
            self.mock_group.update_webhook.reset_mock()

    def test_update_webhook_bad_input_400(self):
        """
        Invalid JSON data is rejected
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        self.assert_status_code(400, None, 'PUT', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_update_webhook_invalid_schema_400(self):
        """
        Webhook schema is obeyed - an empty schema is bad.
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        response_body = self.assert_status_code(400, None, 'PUT', '[]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    def test_update_valid_webhook(self):
        """
        Update webhook returns an empty 204 if successful
        """
        self.mock_group.update_webhook.return_value = defer.succeed(None)
        response_body = self.assert_status_code(
            204, None, 'PUT', json.dumps({'name': 'a name', 'metadata': {}}))
        self.assertEqual(response_body, "")

    def test_delete_webhook_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.delete_webhook.return_value = defer.fail(error)
        self.assert_status_code(500, None, 'DELETE')
        self.mock_group.delete_webhook.assert_called_once_with(
            self.policy_id, self.webhook_id)
        self.flushLoggedErrors(DummyException)

    def test_delete_webhook_for_unknowns_is_404(self):
        """
        When deleting a webhook, endpoint returns a 404 if:
        - the group doesn't exist and :class:`NoSuchScalingGroupError`
        is raised
        - the policy doesn't exist and :class:`NoSuchPolicyError` is raised
        - the webhook doesn't exist and :class:`NoSuchWebhookError` is raised
        """
        errors = [
            NoSuchScalingGroupError(self.tenant_id, self.group_id),
            NoSuchPolicyError(self.tenant_id, self.group_id, self.policy_id),
            NoSuchWebhookError(self.tenant_id, self.group_id, self.policy_id,
                               self.webhook_id)]
        for error in errors:
            self.mock_group.delete_webhook.return_value = defer.fail(error)
            self.assert_status_code(404, None, 'DELETE')
            self.mock_group.delete_webhook.assert_called_once_with(
                self.policy_id, self.webhook_id)
            self.flushLoggedErrors(type(error))
            self.mock_group.delete_webhook.reset_mock()

    def test_delete_valid_webhook(self):
        """
        Delete webhook returns an empty 204 if successful
        """
        self.mock_group.delete_webhook.return_value = defer.succeed(None)
        response_body = self.assert_status_code(
            204, None, 'DELETE')
        self.assertEqual(response_body, "")

    @mock.patch('otter.rest.decorators.log')
    def test_execute_webhook(self, log):
        """
        Execute a webhook by hash returns a 202
        """
        log = log.bind().bind()
        self.mock_store.webhook_info_by_hash.return_value = defer.succeed(
            (self.tenant_id, self.group_id, self.policy_id))

        response_body = self.assert_status_code(
            202, '/v1.0/execute/1/11111/', 'POST')

        self.mock_store.get_scaling_group.assert_called_once_with(
            log.bind(), self.tenant_id, self.group_id)

        self.assertEqual(log.bind.call_args_list[0],
                         mock.call(tenant_id=self.tenant_id, scaling_group_id=self.group_id,
                                   policy_id=self.policy_id))

        self.mock_controller.maybe_execute_scaling_policy.assert_called_once_with(
            log.bind(),
            'transaction-id',
            self.mock_group,
            self.mock_state,
            policy_id=self.policy_id
        )

        self.assertEqual(response_body, '')

    def test_execute_webhook_does_not_wait_for_response(self):
        """
        If the policy execution fails, the webhook should still return 202 and
        does not wait for the response
        """
        self.mock_store.webhook_info_by_hash.return_value = defer.Deferred()

        response_body = self.assert_status_code(
            202, '/v1.0/execute/1/11111/', 'POST')

        self.assertEqual(response_body, '')

    def test_execute_webhook_that_doesnt_exist(self):
        """
        Executing a webhook with an unknown hash should appear to succeed with
        a 202
        """
        self.mock_store.webhook_info_by_hash.return_value = defer.fail(
            UnrecognizedCapabilityError("11111", 1))

        response_body = self.assert_status_code(
            202, '/v1.0/execute/1/11111/', 'POST')

        self.assertEqual(response_body, '')

    def test_execute_webhook_logs_unhandled_exceptions(self):
        """
        Executing a webhook logs any unhandled exceptions.
        """
        exc = ValueError('otters in pants')

        self.mock_store.webhook_info_by_hash.return_value = defer.fail(exc)

        self.assert_status_code(202, '/v1.0/execute/1/11111/', 'POST')

        excs = self.flushLoggedErrors(ValueError)
        self.assertEqual(excs[0].value, exc)

    @mock.patch('otter.rest.decorators.log')
    def test_execute_webhook_logs_info_message_when_policy_cannot_be_executed(self, log):
        """
        Executing a webhook logs an information message about non-fatal, policy
        execution failures.
        """
        cap_log = log.bind.return_value.bind.return_value

        for exc in [CannotExecutePolicyError('tenant', 'group', 'policy', 'test'),
                    NoSuchPolicyError('tenant', 'group', 'policy'),
                    NoSuchScalingGroupError('tenant', 'group'),
                    UnrecognizedCapabilityError("11111", 1)]:
            self.mock_store.webhook_info_by_hash.return_value = defer.succeed(
                ('tenant', 'group', 'policy'))
            self.mock_group.modify_state.side_effect = lambda *args, **kwargs: defer.fail(exc)
            self.assert_status_code(202, '/v1.0/execute/1/11111/', 'POST')

            cap_log.bind().msg.assert_any_call(
                'Non-fatal error during webhook execution: {exc!r}', exc=exc)

            self.assertEqual(0, cap_log.err.call_count)
            self.assertEqual(0, cap_log.bind().err.call_count)
