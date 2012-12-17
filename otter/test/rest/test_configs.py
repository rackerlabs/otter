"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for listing
all scaling groups, and creating/viewing/deleting a scaling group.
"""

import json
from jsonschema import ValidationError

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
    Tests for ``/{tenantId}/groups/{groupId}/config`` endpoints
    """
    skip = "Not implemented yet."

    def test_group_get(self):
        """
        Tries to get a group
        """
        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.view_config.return_value = defer.succeed(request_body)

        self.mock_store.get_scaling_group.return_value = mock_group

        self.assert_status_code(200, self.endpoint + '/one', 'GET')

        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.view_config.assert_called_once_with()

    def test_group_get_404(self):
        """
        Tries to get a group, only to get a 404
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.view_config.return_value = defer.fail(
            NoSuchScalingGroupError('dfw', '11111', 'one'))

        self.mock_store.get_scaling_group.return_value = mock_group

        self.assert_status_code(404, self.endpoint + '/one', 'GET')

        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.view_config.assert_called_once_with()
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_group_modify(self):
        """
        Tries to modify a group
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = None

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(204, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw',
                                                                  'one')
        mock_group.update_config.assert_called_once_with(request_body)

    def test_group_modify_missing_input_400(self):
        """
        Checks that an invalid update won't be called
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = None

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {}

        response_body = self.assert_status_code(400, self.endpoint + '/one',
                                                'PUT',
                                                json.dumps(request_body))
        resp = json.loads(response_body)
        self.assertEqual(resp['type'], 'ValidationError')
        self.assertEqual(mock_group.update_config.called, False)
        self.flushLoggedErrors(ValidationError)

    def test_group_modify_not_found_404(self):
        """
        Checks that if you try to modify a not-found object it fails
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = defer.fail(
            NoSuchScalingGroupError('dfw', '11111', 'one'))

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(404, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        mock_group.update_config.assert_called_once_with(request_body)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_entity_modify_fail_500(self):
        """
        Checks to make sure that if the update fails for some strange
        reason, a 500 is returned
        """
        mock_group = mock.MagicMock()
        mock_group.uuid = 'one'
        mock_group.region = 'dfw'
        mock_group.update_config.return_value = defer.fail(DummyException())

        self.mock_store.get_scaling_group.return_value = mock_group

        request_body = {'name': 'blah', 'cooldown': 60, 'minEntities': 0}

        self.assert_status_code(500, self.endpoint + '/one', 'PUT',
                                json.dumps(request_body))
        self.mock_store.get_scaling_group.assert_called_once_with('11111',
                                                                  'dfw', 'one')
        mock_group.update_config.assert_called_once_with(request_body)
        self.flushLoggedErrors(DummyException)
