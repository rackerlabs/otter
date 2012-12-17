"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for viewing
and updating a scaling group config, and viewing and updating a launch config
for a scaling group.
"""

import json
# from jsonschema import ValidationError

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

# from otter.json_schema.scaling_group import (
#     config_examples, launch_server_config_examples as launch_examples)
from otter.models.interface import NoSuchScalingGroupError
# from otter.rest.decorators import InvalidJsonError

from otter.test.rest.request import DummyException, RestAPITestMixin

# import groups in order to get the routes created - the assignment is a trick
# to ignore pyflakes
import otter.rest.configs as _c
configs = _c


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

        self.assert_status_code(404)

        self.mock_store.get_scaling_group.assert_called_once_with('11111', '1')
        self.mock_group.view_config.assert_called_once_with()
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_get_group_config_500(self):
        """
        Unknown errors return a 500 as a response http code.
        """
        self.mock_group.view_config.return_value = defer.fail(DummyException())
        self.assert_status_code(500)

        self.mock_store.get_scaling_group.assert_called_once_with('11111', '1')
        self.mock_group.view_config.assert_called_once_with()
        self.flushLoggedErrors(DummyException)

    def test_get_group_config_succeeds(self):
        """
        If the group does succeed, an attempt to get the config returns a 200
        and the actual group config
        """
        request_body = {
            'name': 'blah',
            'cooldown': 35,
            'minEntities': 1,
            'maxEntities': 5,
            'metadata': {'something': 'that'}
        }
        self.mock_group.view_config.return_value = defer.succeed(request_body)

        body = self.assert_status_code(200)
        self.assertEqual(json.loads(body), request_body)

        self.mock_store.get_scaling_group.assert_called_once_with('11111', '1')
        self.mock_group.view_config.assert_called_once_with()

    # def test_group_modify_not_found_404(self):
    #     """
    #     Checks that if you try to modify a not-found object it fails
    #     """
    #     mock_group = mock.MagicMock()
    #     mock_group.uuid = 'one'
    #     mock_group.region = 'dfw'
    #     mock_group.update_config.return_value = defer.fail(
    #         NoSuchScalingGroupError('dfw', '11111', 'one'))

    #     self.mock_store.get_scaling_group.return_value = mock_group

    #     request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

    #     self.assert_status_code(404, self.endpoint + '/one', 'PUT',
    #                             json.dumps(request_body))
    #     mock_group.update_config.assert_called_once_with(request_body)
    #     self.flushLoggedErrors(NoSuchScalingGroupError)

    # def test_entity_modify_fail_500(self):
    #     """
    #     Checks to make sure that if the update fails for some strange
    #     reason, a 500 is returned
    #     """
    #     mock_group = mock.MagicMock()
    #     mock_group.uuid = 'one'
    #     mock_group.region = 'dfw'
    #     mock_group.update_config.return_value = defer.fail(DummyException())

    #     self.mock_store.get_scaling_group.return_value = mock_group

    #     request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

    #     self.assert_status_code(500, self.endpoint + '/one', 'PUT',
    #                             json.dumps(request_body))
    #     self.mock_store.get_scaling_group.assert_called_once_with('11111',
    #                                                               'dfw', 'one')
    #     mock_group.update_config.assert_called_once_with(request_body)
    #     self.flushLoggedErrors(DummyException)


    # def test_group_modify(self):
    #     """
    #     Tries to modify a group
    #     """
    #     mock_group = mock.MagicMock()
    #     mock_group.uuid = 'one'
    #     mock_group.region = 'dfw'
    #     mock_group.update_config.return_value = None

    #     self.mock_store.get_scaling_group.return_value = mock_group

    #     request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

    #     self.assert_status_code(204, self.endpoint + '/one', 'PUT',
    #                             json.dumps(request_body))
    #     self.mock_store.get_scaling_group.assert_called_once_with('11111',
    #                                                               'dfw',
    #                                                               'one')
    #     mock_group.update_config.assert_called_once_with(request_body)

    # def test_group_modify_missing_input_400(self):
    #     """
    #     Checks that an invalid update won't be called
    #     """
    #     mock_group = mock.MagicMock()
    #     mock_group.uuid = 'one'
    #     mock_group.region = 'dfw'
    #     mock_group.update_config.return_value = None

    #     self.mock_store.get_scaling_group.return_value = mock_group

    #     request_body = {}

    #     response_body = self.assert_status_code(400, self.endpoint + '/one',
    #                                             'PUT',
    #                                             json.dumps(request_body))
    #     resp = json.loads(response_body)
    #     self.assertEqual(resp['type'], 'ValidationError')
    #     self.assertEqual(mock_group.update_config.called, False)
    #     self.flushLoggedErrors(ValidationError)
