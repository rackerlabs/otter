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

from otter.json_schema.scaling_group import policy_examples
from otter.models.interface import NoSuchPolicyError
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin

# import groups in order to get the routes created - the assignment is a trick
# to ignore pyflakes
import otter.rest.policies as _p
policies = _p


class AllPoliciesTestCase(RestAPITestMixin, TestCase):
    """
    """
    endpoint = "/v1.0/11111/groups/1/policy"
    invalid_methods = ("PUT", "DELETE")

    def test_list_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        (self.mock_group.
            list_policies.
            return_value) = defer.fail(error)
        self.assert_status_code(500)
        self.flushLoggedErrors()

    def test_no_policies_returns_empty_list(self):
        """
        If there are no policies for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        (self.mock_group.
            list_policies.
            return_value) = defer.succeed({})
        body = self.assert_status_code(200)
        self.mock_group.list_policies.assert_called_once()
        self.assertEqual(json.loads(body), {})

    def test_policy_create_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_group.create_policy.return_value = defer.succeed(None)
        self.assert_status_code(400, None, 'POST', '[')
        self.assert_status_code(400, None, 'POST', '{},{}')
        self.flushLoggedErrors(InvalidJsonError)

    def test_policy_create_invalid_schema_400(self):
        """
        Checks that the scaling policy schema is obeyed --
        an empty schema is bad.
        """

        (self.mock_group.
            create_policy.
            return_value) = defer.succeed(None)
        response_body = self.assert_status_code(400, None, 'POST', '["tacos"]')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_policy_create(self, mock_url):
        """
        Tries to create a set of policies.
        """
        (self.mock_group.
            create_policy.
            return_value) = defer.succeed("1")
        request_body = policy_examples
        self.assert_status_code(201, None,
                                'POST', json.dumps(request_body))
        self.mock_group.create_policy.assert_called_once_with(
            policy_examples)


class OnePolicyTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/policy`` endpoint, which updates
    and views the policy part of a scaling group.
    """
    endpoint = "/v1.0/11111/groups/1/policy/1"
    invalid_methods = ("POST")

    def setUp(self):
        """
        Set up a mock group to be used for viewing and updating policies
        """
        self.policy_id = "1"
        super(OnePolicyTestCase, self).setUp()

    def test_view_policy(self):
        """
        Get details of a specific policy.
        """
        (self.mock_group.
            get_policy.
            return_value) = defer.succeed(policy_examples[0])

        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)
        self.mock_group.get_policy.assert_equal(resp, policy_examples[0])

    def test_view_policy_404(self):
        """
        Getting a nonexistant policy results in 404.
        """
        (self.mock_group.
            get_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '111', '1'))

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

        response_body = self.assert_status_code(204, method="PUT",
                                    body=json.dumps(policy_examples[1]))
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with('11111', '1')
        self.mock_group.update_policy.assert_called_once_with(self.policy_id,
             policy_examples[1])

    def test_update_policy_failure_404(self):
        """
        If you try to update a non existant policy, fails with a 404.
        """
        (self.mock_group.
            update_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '1'))

        response_body = self.assert_status_code(
            404, method="PUT", body=json.dumps(policy_examples[0]))
        resp = json.loads(response_body)

        self.mock_group.update_policy.assert_called_once_with(
            self.policy_id, policy_examples[0])
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_policy_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_group.update_policy.return_value = defer.fail(error)
        self.assert_status_code(500, method="PUT",
                                body=json.dumps(policy_examples[1]))
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
        self.mock_store.get_scaling_group.assert_called_once_with('11111', '1')
        self.mock_group.delete_policy.assert_called_once_with(self.policy_id)

    def test_delete_policy_failure_404(self):
        """
        Try to delete a nonexistant policy, fails with a 404.
        """
        (self.mock_group.
            delete_policy.
            return_value) = defer.fail(NoSuchPolicyError('11111', '1'))

        response_body = self.assert_status_code(404, method="DELETE")
        resp = json.loads(response_body)

        self.mock_group.delete_policy.assert_called_once_with(
            self.policy_id)
        self.assertEqual(resp['type'], 'NoSuchPolicyError')
        self.flushLoggedErrors(NoSuchPolicyError)
