"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for viewing
and updating a scaling group config, and viewing and updating a launch config
for a scaling group.
"""

import json
from jsonschema import validate, ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.json_schema.group_examples import (
    config as config_examples,
    launch_server_config as launch_examples)
from otter.json_schema import rest_schemas
from otter.models.interface import NoSuchScalingGroupError
from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin


class GroupConfigTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/config`` endpoint, which updates
    and views the config part of a scaling group (having to do with the min,
    max, and steady state number of entities, as well as the metadata
    associated with the group).
    """
    endpoint = "/v1.0/11111/groups/1/config"
    invalid_methods = ("DELETE", "POST")

    def setUp(self):
        """
        Set up a mock group to be used for viewing and updating configurations
        """
        super(GroupConfigTestCase, self).setUp()
        self.mock_group = mock.MagicMock(
            spec=('uuid', 'view_config', 'update_config'), uuid='1')
        self.mock_store.get_scaling_group.return_value = self.mock_group

    def test_get_group_config_404(self):
        """
        If the group does not exist, an attempt to get the config returns a 404
        """
        self.mock_group.view_config.return_value = defer.fail(
            NoSuchScalingGroupError('11111', '1'))
        response_body = self.assert_status_code(404)
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_config.assert_called_once_with()
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_get_group_config_500(self):
        """
        Unknown errors return a 500 as a response http code.
        """
        self.mock_group.view_config.return_value = defer.fail(DummyException())
        response_body = self.assert_status_code(500)
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_config.assert_called_once_with()
        self.assertEqual(resp['type'], 'InternalError')
        self.flushLoggedErrors(DummyException)

    def test_get_group_config_succeeds(self):
        """
        If the group does succeed, an attempt to get the config returns a 200
        and the actual group config
        """
        config = {
            'name': 'blah',
            'cooldown': 35,
            'minEntities': 1,
            'maxEntities': 5,
            'metadata': {'something': 'that'}
        }
        self.mock_group.view_config.return_value = defer.succeed(config)

        response_body = json.loads(self.assert_status_code(200))
        validate(response_body, rest_schemas.view_config)
        self.assertEqual(response_body, {'groupConfiguration': config})

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_config.assert_called_once_with()

    def test_update_group_config_404(self):
        """
        If you try to modify a not-found object it fails with a 404 not found
        """
        self.mock_group.update_config.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}
        response_body = self.assert_status_code(404, method='PUT',
                                                body=json.dumps(request_body))
        resp = json.loads(response_body)

        self.mock_group.update_config.assert_called_once_with(request_body)
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_update_group_config_fail_500(self):
        """
        If the update fails for some strange reason, a 500 is returned
        """
        self.mock_group.update_config.return_value = defer.fail(
            DummyException())

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}
        response_body = self.assert_status_code(500, method="PUT",
                                                body=json.dumps(request_body))
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.update_config.assert_called_once_with(request_body)
        self.assertEqual(resp['type'], 'InternalError')
        self.flushLoggedErrors(DummyException)

    def test_update_group_config_success(self):
        """
        If the update succeeds, the data is updated and a 204 is returned
        """
        self.mock_group.update_config.return_value = defer.succeed(None)
        request_body = {
            'name': 'blah',
            'cooldown': 35,
            'minEntities': 1,
            'maxEntities': 5,
            'metadata': {'something': 'that'}
        }
        response_body = self.assert_status_code(204, method='PUT',
                                                body=json.dumps(request_body))
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.update_config.assert_called_once_with(request_body)

    def test_group_modify_bad_or_missing_input_400(self):
        """
        Checks that an update with no PUT data will fail with a 400
        """
        for request_body in ("", "{", "adf"):
            self.mock_group.update_config.return_value = None
            response_body = self.assert_status_code(400, method='PUT',
                                                    body=request_body)
            resp = json.loads(response_body)

            self.assertEqual(resp['type'], 'InvalidJsonError')
            self.assertFalse(self.mock_group.update_config.called)
            self.flushLoggedErrors(InvalidJsonError)

    def test_group_modify_bad_schema_400(self):
        """
        Checks that an update with PUT data with the wrong schema fails with a
        400
        """
        invalids = ({"name": "1"}, {},
                    {'name': '1', 'cooldown': 5, 'minEntities': 1, "hat": "2"})
        for request_body in invalids:
            self.mock_group.update_config.return_value = None
            response_body = self.assert_status_code(
                400, method='PUT', body=json.dumps(request_body))
            resp = json.loads(response_body)

            self.assertEqual(resp['type'], 'ValidationError')
            self.assertFalse(self.mock_group.update_config.called)
            self.flushLoggedErrors(ValidationError)


class LaunchConfigTestCase(RestAPITestMixin, TestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/launch`` endpoint, which updates
    and views the launch config part of a scaling group (having to do with
    what kind of server to start up, how to provision it, whether to add it to
    a load balancer, etc.)
    """
    endpoint = "/v1.0/11111/groups/1/launch"
    invalid_methods = ("DELETE", "POST")

    def setUp(self):
        """
        Set up a mock group to be used for viewing and updating configurations
        """
        super(LaunchConfigTestCase, self).setUp()
        self.mock_group = mock.MagicMock(
            spec=('uuid', 'view_launch_config', 'update_launch_config'),
            uuid='1')
        self.mock_store.get_scaling_group.return_value = self.mock_group

    def test_get_launch_config_404(self):
        """
        If the group does not exist, an attempt to get the launch config
        returns a 404
        """
        self.mock_group.view_launch_config.return_value = defer.fail(
            NoSuchScalingGroupError('11111', '1'))
        response_body = self.assert_status_code(404)
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_launch_config.assert_called_once_with()
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_get_launch_config_500(self):
        """
        Unknown errors return a 500 as a response http code.
        """
        self.mock_group.view_launch_config.return_value = defer.fail(
            DummyException())
        response_body = self.assert_status_code(500)
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_launch_config.assert_called_once_with()
        self.assertEqual(resp['type'], 'InternalError')
        self.flushLoggedErrors(DummyException)

    def test_get_launch_config_succeeds(self):
        """
        If getting the group does succeed, an attempt to get the launch config
        returns a 200 and the actual group config
        """
        self.mock_group.view_launch_config.return_value = defer.succeed(
            launch_examples()[0])

        response_body = self.assert_status_code(200)
        resp = json.loads(response_body)
        validate(resp, rest_schemas.view_launch_config)
        self.assertEqual(resp, {'launchConfiguration': launch_examples()[0]})

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.view_launch_config.assert_called_once_with()

    def test_update_group_config_404(self):
        """
        If you try to modify a not-found object it fails with a 404 not found
        """
        self.mock_group.update_launch_config.return_value = defer.fail(
            NoSuchScalingGroupError('11111', 'one'))

        response_body = self.assert_status_code(
            404, method='PUT', body=json.dumps(launch_examples()[0]))
        resp = json.loads(response_body)

        self.mock_group.update_launch_config.assert_called_once_with(
            launch_examples()[0])
        self.assertEqual(resp['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_update_launch_config_fail_500(self):
        """
        If the update fails for some strange reason, a 500 is returned
        """
        self.mock_group.update_launch_config.return_value = defer.fail(
            DummyException())

        response_body = self.assert_status_code(
            500, method="PUT", body=json.dumps(launch_examples()[0]))
        resp = json.loads(response_body)

        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.update_launch_config.assert_called_once_with(
            launch_examples()[0])
        self.assertEqual(resp['type'], 'InternalError')
        self.flushLoggedErrors(DummyException)

    def test_update_launch_config_success(self):
        """
        If the update succeeds, the data is updated and a 204 is returned
        """
        self.mock_group.update_launch_config.return_value = defer.succeed(None)
        response_body = self.assert_status_code(
            204, method='PUT', body=json.dumps(launch_examples()[0]))
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with(mock.ANY, '11111', '1')
        self.mock_group.update_launch_config.assert_called_once_with(
            launch_examples()[0])

    def test_launch_config_modify_bad_or_missing_input_400(self):
        """
        Checks that an update with no PUT data will fail with a 400
        """
        for request_body in ("", "{", "adf"):
            self.mock_group.update_launch_config.return_value = None
            response_body = self.assert_status_code(400, method='PUT',
                                                    body=request_body)
            resp = json.loads(response_body)

            self.assertEqual(resp['type'], 'InvalidJsonError')
            self.assertFalse(self.mock_group.update_launch_config.called)
            self.flushLoggedErrors(InvalidJsonError)

    def test_launch_config_modify_bad_schema_400(self):
        """
        Checks that an update with PUT data with the wrong schema fails with a
        400
        """
        invalids = (config_examples()[0], {"type": "launch_server", "args": {}})
        for request_body in invalids:
            self.mock_group.update_launch_config.return_value = None
            response_body = self.assert_status_code(
                400, method='PUT', body=json.dumps(request_body))
            resp = json.loads(response_body)

            self.assertEqual(resp['type'], 'ValidationError')
            self.assertFalse(self.mock_group.update_launch_config.called)
            self.flushLoggedErrors(ValidationError)
