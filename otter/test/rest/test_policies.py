"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for viewing
and updating a scaling group config, and viewing and updating a launch config
for a scaling group.
"""

import json
from jsonschema import ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.controller import CannotExecutePolicyError
from otter.json_schema.group_examples import policy as policy_examples
from otter.json_schema import rest_schemas, validate
from otter.models.interface import NoSuchPolicyError
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin


class AllPoliciesTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{group_id}/policies`` endpoints (create, list)
    """
    endpoint = "/v1.0/11111/groups/1/policies/"
    invalid_methods = ("PUT", "DELETE")

    def test_list_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.list_policies.return_value = defer.fail(error)
        self.assert_status_code(500)
        self.flushLoggedErrors()

    def test_no_policies_returns_empty_list(self):
        """
        If there are no policies for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        self.mock_group.list_policies.return_value = defer.succeed([])
        response_body = self.assert_status_code(200)
        self.mock_group.list_policies.assert_called_once()

        resp = json.loads(response_body)
        validate(resp, rest_schemas.list_policies_response)
        self.assertEqual(resp, {
            "policies": [],
            "policies_links": []
        })

    def test_policy_dictionary_gets_linkified(self):
        """
        When policies are returned, a properly formed JSON blob containing ids
        and links are returned with a 200 (OK) status
        """
        self.mock_group.list_policies.return_value = defer.succeed(
            [dict(id='5', **policy_examples()[0])])
        response_body = self.assert_status_code(200)
        self.mock_group.list_policies.assert_called_once()

        resp = json.loads(response_body)
        validate(resp, rest_schemas.list_policies_response)
        expected = dict(
            id='5',
            links=[{
                'rel': 'self',
                'href': '/v1.0/11111/groups/1/policies/5/'
            }],
            **policy_examples()[0]
        )

        self.assertEqual(resp, {
            "policies": [expected],
            "policies_links": []
        })

    @mock.patch('otter.rest.policies.get_policies_links')
    def test_pagination(self, get_policies_links):
        """
        `list_policies` and `get_policies_links` is called with pagination arguments
        passed. The returned value from `get_policies_links` is put in 'policies_links'
        """
        get_policies_links.return_value = [{'href': 'someurl', 'rel': 'next'}]
        self.mock_group.list_policies.return_value = defer.succeed([])
        response_body = self.assert_status_code(
            200, endpoint='{}?limit=3&marker=m'.format(self.endpoint))
        self.mock_group.list_policies.assert_called_once_with(limit=3, marker='m')

        resp = json.loads(response_body)
        validate(resp, rest_schemas.list_policies_response)
        get_policies_links.assert_called_once_with(
            [], '11111', '1', None, limit=3, marker='m')
        self.assertEqual(resp['policies_links'], get_policies_links.return_value)

    def test_policies_links_next(self):
        """
        When more than limit policies are returned, a properly formed JSON blob with
        policies_links containing next link is returned with a 200 (OK) status
        """
        self.mock_group.list_policies.return_value = defer.succeed(
            [dict(id='{}'.format(i), **policy_examples()[0])
             for i in range(1, 102)])
        response_body = self.assert_status_code(200)
        self.mock_group.list_policies.assert_called_once()

        resp = json.loads(response_body)
        validate(resp, rest_schemas.list_policies_response)
        expected_links = [
            {'href': '/v1.0/11111/groups/1/policies/?marker=100&limit=100',
             'rel': 'next'}
        ]
        self.assertEqual(resp['policies_links'], expected_links)

    def test_policy_create_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_group.create_policies.return_value = defer.succeed({})
        self.assert_status_code(400, None, 'POST', '[')
        self.assert_status_code(400, None, 'POST', '{},{}')
        self.flushLoggedErrors(InvalidJsonError)

    def test_policy_create_invalid_schema_400(self):
        """
        Checks that the scaling policy schema is obeyed --
        an empty schema is bad.
        """
        self.mock_group.create_policies.return_value = defer.succeed({})
        response_body = self.assert_status_code(400, None, 'POST', '["tacos"]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    def test_policy_create(self):
        """
        Tries to create a set of policies.
        """
        self.mock_group.create_policies.return_value = defer.succeed([
            dict(id="5", **policy_examples()[0])])
        response_body = self.assert_status_code(
            201, None, 'POST', json.dumps(policy_examples()[:1]),
            # location header points to the policy list
            '/v1.0/11111/groups/1/policies/')

        self.mock_group.create_policies.assert_called_once_with(
            policy_examples()[:1])

        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_policies_response)

        expected_policy = policy_examples()[0]
        expected_policy['id'] = '5'
        expected_policy['links'] = [
            {
                'rel': 'self',
                'href': '/v1.0/11111/groups/1/policies/5/'
            }
        ]
        self.assertEqual(resp, {"policies": [expected_policy]})


class OnePolicyTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/policies`` endpoint, which updates
    and views the policy part of a scaling group.
    """
    endpoint = "/v1.0/11111/groups/1/policies/2/"
    invalid_methods = ("POST")
    policy_id = "2"

    def setUp(self):
        """
        Set up common policy mocks.
        """
        super(OnePolicyTestCase, self).setUp()

        controller_patcher = mock.patch('otter.rest.policies.controller')
        self.mock_controller = controller_patcher.start()
        self.addCleanup(controller_patcher.stop)

    def test_get_policy(self):
        """
        Get details of a specific policy.  The response should conform with
        the json schema.
        """
        self.mock_group.get_policy.return_value = defer.succeed(
            policy_examples()[0])

        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)

        validate(resp, rest_schemas.get_policy_response)

        expected = policy_examples()[0]
        expected['id'] = self.policy_id
        expected['links'] = [
            {
                'rel': 'self',
                'href': '/v1.0/11111/groups/1/policies/{0}/'.format(self.policy_id)
            }
        ]
        self.assertEqual(resp, {'policy': expected})

    def test_get_policy_404(self):
        """
        Getting a nonexistant policy results in 404.
        """
        (self.mock_group.
            get_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '1', '2'))

        response_body = self.assert_status_code(404, method="GET")
        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_policy_success(self):
        """
        Replace existing details of a policy with new details.
        """
        (self.mock_group.
            update_policy.
            return_value) = defer.succeed(None)

        response_body = self.assert_status_code(
            204, method="PUT", body=json.dumps(policy_examples()[1]))
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.update_policy.assert_called_once_with(
            self.policy_id, policy_examples()[1])

    def test_update_policy_failure_404(self):
        """
        If you try to update a non existant policy, fails with a 404.
        """
        (self.mock_group.
            update_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '1', '2'))

        response_body = self.assert_status_code(
            404, method="PUT", body=json.dumps(policy_examples()[0]))
        resp = json.loads(response_body)

        self.mock_group.update_policy.assert_called_once_with(
            self.policy_id, policy_examples()[0])
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_policy_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.update_policy.return_value = defer.fail(error)
        self.assert_status_code(500, method="PUT",
                                body=json.dumps(policy_examples()[1]))
        self.flushLoggedErrors()

    def test_policy_update_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_group.update_policy.return_value = defer.succeed(None)
        self.assert_status_code(400, None, 'PUT', '[')
        self.assert_status_code(400, None, 'PUT', '{},{}')
        self.flushLoggedErrors(InvalidJsonError)

    def test_policy_update_invalid_schema_400(self):
        """
        Checks that the scaling policy schema is obeyed --
        an empty schema is bad.
        """

        (self.mock_group.
            update_policy.
            return_value) = defer.succeed(None)
        response_body = self.assert_status_code(400, None, 'PUT', '["tacos"]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    def test_delete_policy_success(self):
        """
        Try to delete a policy.
        """
        (self.mock_group.
            delete_policy.
            return_value) = defer.succeed(None)

        response_body = self.assert_status_code(204, method="DELETE")
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.delete_policy.assert_called_once_with(self.policy_id)

    def test_delete_policy_failure_404(self):
        """
        Try to delete a nonexistant policy, fails with a 404.
        """
        (self.mock_group.
            delete_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '1', '2'))

        response_body = self.assert_status_code(404, method="DELETE")
        resp = json.loads(response_body)

        self.mock_group.delete_policy.assert_called_once_with(
            self.policy_id)
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_execute_policy_success(self):
        """
        Try to execute a policy.
        """
        response_body = self.assert_status_code(202,
                                                endpoint=self.endpoint + 'execute/',
                                                method="POST")
        self.assertEqual(response_body, "{}")
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.assertEqual(self.mock_group.modify_state.call_count, 1)

        self.mock_controller.maybe_execute_scaling_policy.assert_called_once_with(
            mock.ANY,
            'transaction-id',
            self.mock_group,
            self.mock_state,
            policy_id=self.policy_id
        )

    def test_execute_policy_failure_404(self):
        """
        Try to execute a nonexistant policy, fails with a 404.
        """
        self.mock_group.modify_state.side_effect = None
        self.mock_group.modify_state.return_value = defer.fail(
            NoSuchPolicyError('11111', '1', '2'))

        response_body = self.assert_status_code(404,
                                                endpoint=self.endpoint + 'execute/',
                                                method="POST")
        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_execute_policy_failure_403(self):
        """
        If a policy cannot be executed due to cooldowns or budgetary constraints,
        fail with a 403.
        """
        self.mock_group.modify_state.side_effect = None
        self.mock_group.modify_state.return_value = defer.fail(
            CannotExecutePolicyError('11111', '1', '2', 'meh'))

        response_body = self.assert_status_code(403,
                                                endpoint=self.endpoint + 'execute/',
                                                method="POST")
        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'CannotExecutePolicyError')
        self.assertEqual(
            resp['message'],
            'Cannot execute scaling policy 2 for group 1 for tenant 11111: meh')
        self.flushLoggedErrors(CannotExecutePolicyError)

    def test_execute_policy_failure_501(self):
        """
        Try to execute a scale down policy fails with a 501 not implemented.
        """
        self.mock_controller.maybe_execute_scaling_policy.side_effect = (
            NotImplementedError)

        self.assert_status_code(501, endpoint=self.endpoint + 'execute/',
                                method="POST")
        self.flushLoggedErrors(NotImplementedError)
