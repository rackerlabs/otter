"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for listing
all scaling groups, and creating/viewing/deleting a scaling group.
"""
import json
from jsonschema import validate, ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.json_schema.group_examples import (
    launch_server_config as launch_examples,
    config as config_examples,
    policy as policy_examples)

from otter.json_schema import rest_schemas

from otter.models.interface import IScalingGroupState, NoSuchScalingGroupError
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin
from otter.test.utils import iMock


class AllGroupsEndpointTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/`` endpoints (create, list)
    """
    endpoint = "/v1.0/11111/groups/"
    invalid_methods = ("DELETE", "PUT")

    def test_list_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_store.list_scaling_groups.return_value = defer.fail(error)
        self.assert_status_code(500)
        self.flushLoggedErrors()

    def test_create_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        request_body = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0]
        }
        self.mock_store.create_scaling_group.return_value = defer.fail(error)
        self.assert_status_code(500, method="POST",
                                body=json.dumps(request_body))
        self.flushLoggedErrors()

    def test_no_groups_returns_empty_list(self):
        """
        If there are no groups for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        self.mock_store.list_scaling_groups.return_value = defer.succeed([])
        body = self.assert_status_code(200)
        self.mock_store.list_scaling_groups.assert_called_once_with(mock.ANY, '11111')

        resp = json.loads(body)
        self.assertEqual(resp, {"groups": [], "groups_links": []})
        validate(resp, rest_schemas.list_groups_response)

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_returned_group_list_gets_translated(self, mock_url):
        """
        Test that the scaling groups list gets translated into a list of
        scaling group ids and links.
        """
        # return two mock scaling group objects
        self.mock_store.list_scaling_groups.return_value = defer.succeed([
            mock.MagicMock(spec=['uuid'], uuid="1"),
            mock.MagicMock(spec=['uuid'], uuid="2")
        ])
        body = self.assert_status_code(200)
        self.mock_store.list_scaling_groups.assert_called_once_with(mock.ANY, '11111')

        resp = json.loads(body)
        validate(resp, rest_schemas.list_groups_response)
        self.assertEqual(resp, {
            "groups": [
                {
                    'id': '1',
                    'links': [
                        {"href": '/v1.0/11111/groups/1/', "rel": "self"},
                    ]
                },
                {
                    'id': '2',
                    'links': [
                        {"href": '/v1.0/11111/groups/2/', "rel": "self"},
                    ]
                }
            ],
            "groups_links": []
        })

    def test_group_create_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed("1")
        self.assert_status_code(400, None, 'POST', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_group_create_invalid_schema_400(self):
        """
        Checks that the scaling groups schema is obeyed --
        an empty schema is bad.
        """

        self.mock_store.create_scaling_group.return_value = defer.succeed("1")
        response_body = self.assert_status_code(400, None, 'POST', '{}')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def _test_successful_create(self, request_body, mock_url):
        """
        Tries to create a scaling group with the given request body (which
        should succeed) - and test the response
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed("1")
        response_body = self.assert_status_code(
            201, None, 'POST', json.dumps(request_body), '/v1.0/11111/groups/1/')
        self.mock_store.create_scaling_group.assert_called_once_with(
            mock.ANY, '11111',
            request_body['groupConfiguration'],
            request_body['launchConfiguration'],
            request_body.get('scalingPolicies', None)
        )
        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_group_response)

        expected = {
            "id": "1",
            "links": [
                {"href": "/v1.0/11111/groups/1/", "rel": "self"},
            ],
            'groupConfiguration': request_body['groupConfiguration'],
            'launchConfiguration': request_body['launchConfiguration']
        }
        if 'scalingPolicies' in request_body:
            expected['scalingPolicies'] = request_body['scalingPolicies']
        self.assertEqual(resp, {"group": expected})

    def test_group_create_one_policy(self):
        """
        Tries to create a scaling group
        """
        self._test_successful_create({
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
            'scalingPolicies': [policy_examples()[0]]
        })

    def test_group_create_many_policies(self):
        """
        Tries to create a scaling group
        """
        self._test_successful_create({
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
            'scalingPolicies': policy_examples()
        })

    def test_group_create_no_scaling_policies(self):
        """
        Tries to create a scaling group, but if no scaling policy is provided
        the the interface is called with None in place of scaling policies
        """
        self._test_successful_create({
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
        })


class OneGroupTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/`` endpoints (view manifest,
    view state, delete)
    """
    endpoint = "/v1.0/11111/groups/one/"
    invalid_methods = ("POST", "PUT")  # cannot update in bulk

    def setUp(self):
        """
        Set the uuid of the group to "one"
        """
        super(OneGroupTestCase, self).setUp()
        self.mock_group.uuid = "one"

    def test_view_manifest_404(self):
        """
        Viewing the manifest of a non-existant group fails with a 404.
        """
        self.mock_group.view_manifest.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        response_body = self.assert_status_code(404, method="GET")
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_manifest.assert_called_once_with()

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_view_manifest(self, url_root):
        """
        Viewing the manifest of an existant group returns whatever the
        implementation's `view_manifest()` method returns, in string format
        """
        manifest = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
            'scalingPolicies': {"5": policy_examples()[0]}
        }
        self.mock_group.view_manifest.return_value = defer.succeed(manifest)

        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)
        validate(resp, rest_schemas.view_manifest_response)

        expected_policy = policy_examples()[0]
        expected_policy.update({
            "id": "5",
            "links": [
                {"href": "/v1.0/11111/groups/one/policies/5/", "rel": "self"},
            ]
        })

        expected = {
            'group': {
                'groupConfiguration': config_examples()[0],
                'launchConfiguration': launch_examples()[0],
                'scalingPolicies': [expected_policy],
                "id": "one",
                "links": [
                    {"href": "/v1.0/11111/groups/one/", "rel": "self"}
                ]
            }
        }
        self.assertEqual(resp, expected)

        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_manifest.assert_called_once_with()

    def test_group_delete(self):
        """
        Deleting an existing group succeeds with a 204.
        """
        self.mock_store.delete_scaling_group.return_value = defer.succeed(None)

        response_body = self.assert_status_code(204, method="DELETE")
        self.assertEqual(response_body, "")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')

    def test_group_delete_404(self):
        """
        Deleting a non-existant group fails with a 404.
        """
        self.mock_store.delete_scaling_group.return_value = defer.fail(
            NoSuchScalingGroupError('11111', '1'))

        response_body = self.assert_status_code(404, method="DELETE")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)


class GroupStateTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/state/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/state/"
    invalid_methods = ("DELETE", "POST", "PUT")  # cannot update in bulk

    def setUp(self):
        """
        Set the uuid of the group to "one"
        """
        super(GroupStateTestCase, self).setUp()
        self.mock_group.uuid = "one"

    def test_view_state_404(self):
        """
        Viewing the state of a non-existant group fails with a 404.
        """
        self.mock_group.view_state.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        response_body = self.assert_status_code(404, method="GET")
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_state.assert_called_once_with()

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    @mock.patch('otter.rest.application.get_url_root', return_value="")
    def test_view_state(self, url_root):
        """
        Viewing the state of an existant group returns whatever the
        implementation's `view_state()` method returns, in string format, with
        the links reformatted so that they a list of dictionaries containing
        the attributes "id" and "links"
        """
        def make_link(rel):
            return {
                "rel": "rel",
                "href": "http://{0}".format(rel)
            }

        self.mock_group.view_state.return_value = defer.succeed({
            'active': {
                "1": [make_link("rel")],
                "2": [make_link("rel")]
            },
            'pending': {
                "3": [make_link("rel")]
            },
            'steadyState': 5,
            'paused': False
        })

        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)

        validate(resp, rest_schemas.group_state)
        self.assertEqual(resp, {"group": {
            'active': [
                {'id': '1', 'links': [make_link("rel")]},
                {'id': '2', 'links': [make_link("rel")]}
            ],
            'pending': [{'id': '3', 'links': [make_link("rel")]}],
            'steadyState': 5,
            'paused': False,
            'id': "one",
            "links": [
                {"href": "/v1.0/11111/groups/one/", "rel": "self"},
            ]
        }})

        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_state.assert_called_once_with()


class GroupPauseTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/pause/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/pause/"
    invalid_methods = ("DELETE", "GET", "PUT")

    def setUp(self):
        """
        Set the uuid of the group to "one"
        """
        super(GroupPauseTestCase, self).setUp()
        self.mock_group = iMock(IScalingGroupState)
        self.mock_store.get_scaling_group.return_value = self.mock_group
        self.mock_group.uuid = "one"

        pause_patch = mock.patch(
            'otter.rest.groups.controller.pause_scaling_group',
            return_value=defer.succeed(None))
        self.mock_pause = pause_patch.start()
        self.addCleanup(pause_patch.stop)

        transaction_patch = mock.patch(
            'otter.rest.decorators.generate_transaction_id',
            return_value="transaction!")
        transaction_patch.start()
        self.addCleanup(transaction_patch.stop)

    def test_pause(self):
        """
        Pausing should call the controller's ``pause_scaling_group`` function
        """
        response_body = self.assert_status_code(204, method="POST")
        self.assertEqual(response_body, "")

        self.mock_pause.assert_called_once_with(mock.ANY, 'transaction!',
                                                self.mock_group)


class GroupResumeTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/resume/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/resume/"
    invalid_methods = ("DELETE", "GET", "PUT")

    def setUp(self):
        """
        Set the uuid of the group to "one"
        """
        super(GroupResumeTestCase, self).setUp()
        self.mock_group = iMock(IScalingGroupState)
        self.mock_store.get_scaling_group.return_value = self.mock_group
        self.mock_group.uuid = "one"

        resume_patch = mock.patch(
            'otter.rest.groups.controller.resume_scaling_group',
            return_value=defer.succeed(None))
        self.mock_resume = resume_patch.start()
        self.addCleanup(resume_patch.stop)

        transaction_patch = mock.patch(
            'otter.rest.decorators.generate_transaction_id',
            return_value="transaction!")
        transaction_patch.start()
        self.addCleanup(transaction_patch.stop)

    def test_resume(self):
        """
        Resume should call the controller's ``resume_scaling_group`` function
        """
        response_body = self.assert_status_code(204, method="POST")
        self.assertEqual(response_body, "")

        self.mock_resume.assert_called_once_with(mock.ANY, 'transaction!',
                                                 self.mock_group)
