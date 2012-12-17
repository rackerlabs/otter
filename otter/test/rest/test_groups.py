"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for listing
all scaling groups, and creating/viewing/deleting a scaling group.
"""

import json
from jsonschema import ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.json_schema.scaling_group import (
    config_examples, launch_server_config_examples as launch_examples)
from otter.models.interface import NoSuchScalingGroupError
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin

# import groups in order to get the routes created - the assignment is a trick
# to ignore pyflakes
import otter.rest.groups as _g
groups = _g


class AllGroupsEndpointTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups`` endpoints (create, list)
    """
    endpoint = "/v1.0/11111/groups"
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
            'groupConfiguration': config_examples[0],
            'launchConfiguration': launch_examples[0]
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
        self.mock_store.list_scaling_groups.assert_called_once_with('11111')
        self.assertEqual(json.loads(body), [])

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
        self.mock_store.list_scaling_groups.assert_called_once_with('11111')
        self.assertEqual(json.loads(body), [
            {
                'id': '1',
                'links': [
                    {"href": '/v1.0/11111/groups/1', "rel": "self"},
                    {"href": '/11111/groups/1', "rel": "bookmark"}
                ]
            },
            {
                'id': '2',
                'links': [
                    {"href": '/v1.0/11111/groups/2', "rel": "self"},
                    {"href": '/11111/groups/2', "rel": "bookmark"}
                ]
            }
        ])

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
    def test_group_create(self, mock_url):
        """
        Tries to create a scaling group
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed("1")
        request_body = {
            'groupConfiguration': config_examples[0],
            'launchConfiguration': launch_examples[0]
        }
        self.assert_status_code(201, None,
                                'POST', json.dumps(request_body),
                                '/v1.0/11111/groups/1')
        self.mock_store.create_scaling_group.assert_called_once_with(
            '11111', request_body)


class OneGroupTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}`` endpoints (view manifest,
    view state, delete)
    """
    endpoint = "/v1.0/11111/groups/one"
    invalid_methods = ("POST", "PUT")  # cannot update in bulk

    def test_group_delete(self):
        """
        Deleting an existing group succeeds with a 204.
        """
        self.mock_store.delete_scaling_group.return_value = defer.succeed(None)

        response_body = self.assert_status_code(204, method="DELETE")
        self.assertEqual(response_body, "")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            '11111', 'one')

    def test_group_delete_404(self):
        """
        Deleting a non-existant group fails with a 404.
        """
        self.mock_store.delete_scaling_group.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        response_body = self.assert_status_code(404, method="DELETE")
        self.mock_store.delete_scaling_group.assert_called_once_with(
            '11111', 'one')

        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)
