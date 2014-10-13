"""
Tests for :mod:`otter.rest.groups`, which include the endpoints for listing
all scaling groups, and creating/viewing/deleting a scaling group.
"""
import json
from jsonschema import ValidationError
from copy import deepcopy

import mock

from twisted.internet import defer
from twisted.trial.unittest import SynchronousTestCase
from twisted.web.http import Request
from twisted.web.test.requesthelper import DummyChannel

from otter.json_schema.group_examples import (
    launch_server_config as launch_examples,
    config as config_examples,
    policy as policy_examples)

from otter.json_schema import rest_schemas, validate
from otter.json_schema.group_schemas import MAX_ENTITIES

from otter.models.interface import (
    GroupState, GroupNotEmptyError, NoSuchScalingGroupError)
from otter.rest.decorators import InvalidJsonError, InvalidQueryArgument

from otter.rest import groups
from otter.rest.groups import format_state_dict, extract_bool_arg

from otter.test.rest.request import DummyException, RestAPITestMixin
from otter.test.utils import patch, matches, IsBoundWith

from otter.rest.bobby import set_bobby
from otter.bobby import BobbyClient

from otter.supervisor import set_supervisor, ServerNotFoundError, CannotDeleteServerBelowMinError
from otter.worker.validate_config import InvalidLaunchConfiguration

from otter.util.config import set_config_data


class FormatterHelpers(SynchronousTestCase):
    """
    Tests for formatting helpers in :mod:`otter.rest.groups`
    """
    def setUp(self):
        """
        Patch url root
        """
        patch(self, 'otter.util.http.get_url_root', return_value="")

    def test_format_state_dict_has_active_and_pending(self):
        """
        :func:`otter.rest.groups.format_state_dict` transforms a
        :class:`GroupState` into the state dictionary that is returned by the
        rest API (minus extra stuff like wrapping it in an extra dictionary
        with the keyword 'group', etc.)

        When there are active servers, this dictionary includes a list of
        active server links and ids.
        """
        active = {
            '1': {'name': 'n1', 'links': ['links1'], 'created': 't'},
            '2': {'name': 'n2', 'links': ['links2'], 'created': 't'},
            '3': {'name': 'n3', 'links': ['links3'], 'created': 't'}}
        pending = {
            'j1': {'created': 't'},
            'j2': {'created': 't'},
            'j3': {'created': 't'}}
        translated = format_state_dict(
            GroupState('11111', 'one', 'test', active, pending, None, {}, True))

        # sort so it can be compared
        translated['active'].sort(key=lambda x: x['id'])

        self.assertEqual(translated, {
            'active': [
                {'id': '1', 'links': ['links1']},
                {'id': '2', 'links': ['links2']},
                {'id': '3', 'links': ['links3']}
            ],
            'name': 'test',
            'activeCapacity': 3,
            'pendingCapacity': 3,
            'desiredCapacity': 6,
            'paused': True
        })


class ExtractBoolArgTests(SynchronousTestCase):
    """
    Tests for :func:`otter.rest.groups.extract_bool_arg`
    """

    def setUp(self):
        """
        Sample request
        """
        self.request = Request(DummyChannel(), True)
        self.request.args = {'key': ['false']}

    def test_no_key(self):
        """
        Request with no key returns default
        """
        self.request.args = {}
        self.assertFalse(extract_bool_arg(self.request, 'key', False))

    def test_valid_key(self):
        """
        Request with valid key gets correct value
        """
        self.assertFalse(extract_bool_arg(self.request, 'key', False))

    def test_valid_true_key(self):
        """
        Request with valid key with value "true" gets correct value
        """
        self.request.args = {'key': ['true']}
        self.assertTrue(extract_bool_arg(self.request, 'key', False))

    def test_mixed_case_key(self):
        """
        Mixed case value for key works
        """
        self.request.args['key'][0] = 'FaLse'
        self.assertFalse(extract_bool_arg(self.request, 'key', False))

    def test_invalid_key(self):
        """
        Invalid key raises InvalidQueryArgument
        """
        self.request.args['key'][0] = 'junk'
        e = self.assertRaises(InvalidQueryArgument, extract_bool_arg,
                              self.request, 'key', False)
        self.assertEqual(
            e.message,
            ('Invalid "key" query argument: "junk". Must be "true" or "false". '
             'Defaults to "false" if not provided'))


class AllGroupsEndpointTestCase(RestAPITestMixin, SynchronousTestCase):
    """
    Tests for ``/{tenantId}/groups/`` endpoints (create, list)
    """
    endpoint = "/v1.0/11111/groups/"
    invalid_methods = ("DELETE", "PUT")

    def setUp(self):
        """
        Mock modify state
        """
        super(AllGroupsEndpointTestCase, self).setUp()
        self.mock_controller = patch(self, 'otter.rest.groups.controller')

        # Patch supervisor
        self.supervisor = mock.Mock(spec=['validate_launch_config'])
        self.supervisor.validate_launch_config.return_value = defer.succeed(None)
        set_supervisor(self.supervisor)

        set_config_data({'limits': {'pagination': 100}, 'url_root': ''})

    def tearDown(self):
        """
        Reset the supervisor
        """
        set_supervisor(None)
        set_config_data({})

    def test_list_unknown_error_is_500(self):
        """
        If an unexpected exception is raised, endpoint returns a 500.
        """
        error = DummyException('what')
        self.mock_store.list_scaling_group_states.return_value = defer.fail(error)
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

    def test_create_invalid_launch_config(self):
        """
        Invalid launch configuration raises 400
        """
        self.supervisor.validate_launch_config.return_value = defer.fail(
            InvalidLaunchConfiguration('meh'))
        request_body = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0]
        }
        self.assert_status_code(400, method='POST',
                                body=json.dumps(request_body))
        self.flushLoggedErrors()

    def test_no_groups_returns_empty_list(self):
        """
        If there are no groups for that account, a JSON blob consisting of an
        empty list is returned with a 200 (OK) status
        """
        self.mock_store.list_scaling_group_states.return_value = defer.succeed([])
        body = self.assert_status_code(200)
        self.mock_store.list_scaling_group_states.assert_called_once_with(
            mock.ANY, '11111', limit=100)

        resp = json.loads(body)
        self.assertEqual(resp, {"groups": [], "groups_links": []})
        validate(resp, rest_schemas.list_groups_response)

    @mock.patch('otter.rest.groups.format_state_dict', return_value={'id': 'formatted'})
    def test_list_group_formats_gets_and_formats_all_states(self, mock_format):
        """
        ``list_all_scaling_groups`` translates a list of IScalingGroup to a
        list of states that are all formatted
        """
        states = [
            GroupState('11111', '2', '', {}, {}, None, {}, False),
            GroupState('11111', '2', '', {}, {}, None, {}, False)
        ]

        self.mock_store.list_scaling_group_states.return_value = defer.succeed(states)

        self.assert_status_code(200)
        self.mock_store.list_scaling_group_states.assert_called_once_with(
            mock.ANY, '11111', limit=100)

        mock_format.assert_has_calls([mock.call(state) for state in states])
        self.assertEqual(len(mock_format.mock_calls), 2)

    @mock.patch('otter.rest.groups.get_autoscale_links',
                return_value=[{'href': 'hey', 'rel': 'self'}])
    def test_list_group_returns_valid_schema(self, *args):
        """
        ``list_all_scaling_groups`` produces a response has the correct schema
        so long as format returns the right value
        """
        self.mock_store.list_scaling_group_states.return_value = defer.succeed(
            [GroupState('11111', '1', '', {}, {1: {}}, None, {}, False)]
        )

        body = self.assert_status_code(200)
        resp = json.loads(body)
        validate(resp, rest_schemas.list_groups_response)
        self.assertEqual(resp, {
            "groups": [{
                'id': '1',
                'links': [{'href': 'hey', 'rel': 'self'}],
                'state': {
                    'active': [],
                    'name': '',
                    'activeCapacity': 0,
                    'pendingCapacity': 1,
                    'desiredCapacity': 1,
                    'paused': False
                }
            }],
            "groups_links": []
        })

    def test_list_group_passes_limit_query(self):
        """
        ``list_all_scaling_groups`` passes on the 'limit' query argument to
        the model
        """
        self.mock_store.list_scaling_group_states.return_value = defer.succeed([])
        self.assert_status_code(
            200, endpoint="{0}?limit=5".format(self.endpoint))
        self.mock_store.list_scaling_group_states.assert_called_once_with(
            mock.ANY, '11111', limit=5)

    def test_list_group_invalid_limit_query_400(self):
        """
        ``list_all_scaling_groups``, if passed an invalid query limit, returns
        a 400
        """
        self.assert_status_code(
            400, endpoint="{0}?limit=blargh".format(self.endpoint))
        self.assertFalse(self.mock_store.list_scaling_group_states.called)

    def test_list_group_passes_marker_query(self):
        """
        ``list_all_scaling_groups`` passes on the 'marker' query argument to
        the model
        """
        self.mock_store.list_scaling_group_states.return_value = defer.succeed([])
        self.assert_status_code(
            200, endpoint="{0}?marker=123456".format(self.endpoint))
        self.mock_store.list_scaling_group_states.assert_called_once_with(
            mock.ANY, '11111', marker='123456', limit=100)

    def test_list_groups_returns_next_link_formatted(self):
        """
        The "next" link should be formatted as link json with the rel 'next'
        """
        self.mock_store.list_scaling_group_states.return_value = defer.succeed([
            GroupState('11111', 'one', 'test', {}, {}, None, {}, True)
        ])
        response_body = self.assert_status_code(
            200, endpoint="{0}?limit=1".format(self.endpoint))
        resp = json.loads(response_body)

        validate(resp, rest_schemas.list_groups_response)
        self.assertEqual(
            resp['groups_links'],
            [{'href': self.endpoint + '?limit=1&marker=one', 'rel': 'next'}])

    def test_group_create_bad_input_400(self):
        """
        Checks that the serialization checks and rejects unserializable
        data
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed({
            'groupConfiguration': 'config',
            'launchConfiguration': 'launch',
            'scalingPolicies': [],
            'id': '1',
            'state': GroupState('11111', '2', '', {}, {}, None, {}, False)
        })
        self.assert_status_code(400, None, 'POST', '{')
        self.flushLoggedErrors(InvalidJsonError)

    def test_create_invalid_server_metadata_in_launch_config(self):
        """
        Invalid launch configuration raises 400
        """
        launch = launch_examples()[0]
        launch['args']['server']['metadata'] = "invalid"

        request_body = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch
        }
        self.assert_status_code(400, method='POST',
                                body=json.dumps(request_body))
        self.flushLoggedErrors()

    def test_group_create_invalid_schema_400(self):
        """
        Checks that the scaling groups schema is obeyed --
        an empty schema is bad.
        """
        self.mock_store.create_scaling_group.return_value = defer.succeed({
            'groupConfiguration': 'config',
            'launchConfiguration': 'launch',
            'scalingPolicies': [],
            'id': '1',
            'state': GroupState('11111', '2', '', {}, {}, None, {}, False)
        })
        response_body = self.assert_status_code(400, None, 'POST', '{}')
        self.flushLoggedErrors(ValidationError)

        resp = json.loads(response_body)
        self.assertEqual(resp['error']['type'], 'ValidationError')

    def test_group_create_maxEntites_lt_minEntities_invalid_400(self):
        """
        minEntities > maxEntities results in a 400.
        """
        expected_config = {
            "name": "group",
            "minEntities": 20,
            "maxEntities": 10,
            "cooldown": 10,
            "metadata": {}
        }

        rval = {
            'groupConfiguration': expected_config,
            'launchConfiguration': launch_examples()[0],
            'id': '1',
            'state': GroupState('11111', '2', '', {}, {}, None, {}, False),
            'scalingPolicies': []
        }

        self.mock_store.create_scaling_group.return_value = defer.succeed(rval)

        invalid = {
            'groupConfiguration': expected_config,
            'launchConfiguration': launch_examples()[0],
            'scalingPolicies': [],
        }
        resp_body = self.assert_status_code(400, self.endpoint, 'POST', json.dumps(invalid))
        resp = json.loads(resp_body)
        self.assertEqual(resp['error']['type'], 'InvalidMinEntities', resp['error']['message'])

    @mock.patch('otter.util.http.get_url_root', return_value="")
    def _test_successful_create(self, request_body, mock_url):
        """
        Tries to create a scaling group with the given request body (which
        should succeed) - and test the response
        """
        config = request_body['groupConfiguration']
        launch = request_body['launchConfiguration']
        policies = request_body.get('scalingPolicies', [])
        state = GroupState('11111', '1', '', {}, {}, None, {}, False)

        expected_config = config.copy()
        expected_config.setdefault('maxEntities', MAX_ENTITIES)
        expected_config.setdefault('metadata', {})

        return_policies = [dict(id=str(i), **p) for i, p in enumerate(policies)]

        rval = {
            'groupConfiguration': expected_config,
            'launchConfiguration': launch,
            'state': state,
            'scalingPolicies': return_policies,
            'id': '1'
        }

        self.mock_store.create_scaling_group.return_value = defer.succeed(rval)

        response_body = self.assert_status_code(
            201, None, 'POST', json.dumps(request_body), '/v1.0/11111/groups/1/')

        self.mock_store.create_scaling_group.assert_called_once_with(
            mock.ANY, '11111', expected_config, launch, policies or None)

        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_and_manifest_response)
        # compare the policies separately, because they have links and may be
        # in a different order
        resp_policies = resp['group'].pop('scalingPolicies')
        resp_policies_links = resp['group'].pop('scalingPolicies_links')

        self.assertEqual(resp, {
            'group': {
                'groupConfiguration': expected_config,
                'launchConfiguration': launch,
                'id': '1',
                'state': format_state_dict(state),
                'links': [{"href": "/v1.0/11111/groups/1/", "rel": "self"}]
            }
        })

        resp_policies.sort(key=lambda dictionary: dictionary['id'])
        for pol in resp_policies:
            self.assertEqual(pol.pop('links'), [{
                "href": "/v1.0/11111/groups/1/policies/{0}/".format(pol.pop('id')),
                "rel": "self"
            }])
        self.assertEqual(resp_policies, policies)

        self.assertEqual(resp_policies_links,
                         [{'href': '/v1.0/11111/groups/1/policies/', 'rel': 'policies'}])

    def test_group_create_maxEntities_eq_minEntities_valid(self):
        """
        A scaling group in which the minEntities == maxEntities validates
        """
        self._test_successful_create({
            'groupConfiguration': {
                "name": "group",
                "minEntities": 10,
                "maxEntities": 10,
                "cooldown": 10,
                "metadata": {}
            },
            'launchConfiguration': launch_examples()[0]
        })

    def test_group_create_default_maxentities(self):
        """
        A scaling group without maxentities defaults to configured maxEntities
        """
        self._test_successful_create({
            'groupConfiguration': {
                "name": "group",
                "minEntities": 10,
                "cooldown": 10,
                "metadata": {}
            },
            'launchConfiguration': launch_examples()[0]
        })

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

    def test_group_create_calls_obey_config_changes(self):
        """
        If the group creation succeeds, ``obey_config_change`` is called with
        the updated log, transaction id, config, group, state, and launch
        config
        """
        config = config_examples()[0]
        launch = launch_examples()[0]

        expected_config = config.copy()
        expected_config.setdefault('maxEntities', 25)
        expected_config.setdefault('metadata', {})

        manifest = {
            'groupConfiguration': expected_config,
            'launchConfiguration': launch
        }
        self.mock_store.create_scaling_group.return_value = defer.succeed(manifest)
        self._test_successful_create(manifest)

        self.mock_group.modify_state.assert_called_once_with(mock.ANY)
        self.mock_controller.obey_config_change.assert_called_once_with(
            mock.ANY, "transaction-id", expected_config, self.mock_group,
            self.mock_state, launch_config=launch)

    def test_create_group_propagates_modify_state_errors(self):
        """
        If there is an error when modify state is called, even if the group
        creation succeeds, a 500 is returned.
        """
        self.mock_group.modify_state.side_effect = AssertionError
        config = config_examples()[0]
        launch = launch_examples()[0]

        self.mock_store.create_scaling_group.return_value = defer.succeed({
            'groupConfiguration': config,
            'launchConfiguration': launch,
            'scalingPolicies': [],
            'id': '1'
        })

        self.assert_status_code(500, None, 'POST', body=json.dumps({
            'groupConfiguration': config,
            'launchConfiguration': launch
        }))
        self.flushLoggedErrors(AssertionError)

    def test_create_group_normalizes_launch_config_null_server_metadata(self):
        """
        If the user passes in null for server metadata in the launch config,
        create group first normalizes it before calling the model
        """
        config = config_examples()[0]

        launch = launch_examples()[0]
        launch['args']['server']['metadata'] = None

        expected_launch = launch_examples()[0]
        expected_launch['args']['server'].pop('metadata', None)

        rval = {
            'groupConfiguration': config,
            'launchConfiguration': expected_launch,
            'id': '1',
            'state': GroupState('11111', '2', '', {}, {}, None, {}, False),
            'scalingPolicies': []
        }

        self.mock_store.create_scaling_group.return_value = defer.succeed(rval)

        self.assert_status_code(
            201, None, 'POST',
            json.dumps({
                'groupConfiguration': config, 'launchConfiguration': launch
            }),
            '/v1.0/11111/groups/1/')

        self.mock_store.create_scaling_group.assert_called_once_with(
            mock.ANY, mock.ANY, mock.ANY, expected_launch, None)


class AllGroupsBobbyEndpointTestCase(RestAPITestMixin, SynchronousTestCase):
    """
    Tests for ``/{tenantId}/groups/`` endpoints (create, list) with Bobby

    This will go away, just here so that we've got the start for optional
    Bobby support in Otter.
    """
    endpoint = "/v1.0/11111/groups/"
    invalid_methods = ("DELETE", "PUT")

    def setUp(self):
        """
        Set up mock Bobby client
        """
        set_bobby(BobbyClient("http://127.0.0.1:9876/"))

        super(AllGroupsBobbyEndpointTestCase, self).setUp()
        self.mock_controller = patch(self, 'otter.rest.groups.controller')
        set_config_data({'url_root': ''})
        self.addCleanup(set_config_data, {})

        # Patch supervisor
        supervisor = mock.Mock(spec=['validate_launch_config'])
        supervisor.validate_launch_config.return_value = defer.succeed(None)
        set_supervisor(supervisor)

    def tearDown(self):
        """
        Revert mock Bobby client
        """
        set_bobby(None)
        set_supervisor(None)

    @mock.patch('otter.util.http.get_url_root', return_value="")
    @mock.patch('otter.bobby.BobbyClient.create_group', return_value=defer.succeed(''))
    def test_group_create_bobby(self, create_group, get_url_root):
        """
        A scaling group is created and calls over to Bobby
        """
        request_body = {
            'groupConfiguration': {
                "name": "group",
                "minEntities": 1,
                "maxEntities": 10,
                "cooldown": 10,
                "metadata": {}
            },
            'launchConfiguration': launch_examples()[0]
        }

        config = request_body['groupConfiguration']
        launch = request_body['launchConfiguration']
        policies = request_body.get('scalingPolicies', [])

        expected_config = config.copy()

        rval = {
            'groupConfiguration': expected_config,
            'launchConfiguration': launch,
            'scalingPolicies': policies,
            'id': '1',
            'state': GroupState('11111', '1', '', {}, {}, None, {}, False)
        }

        self.mock_store.create_scaling_group.return_value = defer.succeed(rval)

        self.assert_status_code(
            201, None, 'POST', json.dumps(request_body), '/v1.0/11111/groups/1/')

        self.mock_store.create_scaling_group.assert_called_once_with(
            mock.ANY, '11111', expected_config, launch, policies or None)

        create_group.assert_called_once_with('11111', '1')


class OneGroupTestCase(RestAPITestMixin, SynchronousTestCase):
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
        self.mock_group.view_manifest.assert_called_once_with(False)

        resp = json.loads(response_body)
        self.assertEqual(resp['error']['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    @mock.patch('otter.rest.groups.get_policies_links', return_value='pol links')
    def test_get_policies_links_called(self, mock_get_policies_links):
        """
        'scalingPolicies_links' is added in response by calling `get_policies_links`
        """
        policies = [dict(id="5", **policy_examples()[0])]
        manifest = {
            'id': 'one',
            'state': GroupState('11111', '1', '', {}, {}, None, {}, False),
            'scalingPolicies': policies
        }
        self.mock_group.view_manifest.return_value = defer.succeed(manifest)
        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)
        self.assertEqual(resp['group']['scalingPolicies_links'], 'pol links')
        mock_get_policies_links.assert_called_once_with(
            policies, '11111', 'one', rel='policies')

    def test_view_manifest(self):
        """
        Viewing the manifest of an existant group returns whatever the
        implementation's `view_manifest()` method returns, in string format
        """
        manifest = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
            'id': 'one',
            'state': GroupState('11111', '1', '', {}, {}, None, {}, False),
            'scalingPolicies': [dict(id="5", **policy_examples()[0])]
        }
        self.mock_group.view_manifest.return_value = defer.succeed(manifest)

        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_and_manifest_response)

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
                ],
                'scalingPolicies_links': [
                    {"href": "/v1.0/11111/groups/one/policies/", "rel": "policies"}
                ],
                'state': manifest['state']
            }
        }
        self.assertEqual(resp, expected)

        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_manifest.assert_called_once_with(False)

    def test_view_manifest_with_webhooks(self):
        """
        `view_manifest` gives webhooks information in policies if query args contains
        ?webhooks=true
        """
        manifest = {
            'groupConfiguration': config_examples()[0],
            'launchConfiguration': launch_examples()[0],
            'id': 'one',
            'state': GroupState('11111', '1', '', {}, {}, None, {}, False),
            'scalingPolicies': [dict(id="5", **policy_examples()[0]),
                                dict(id="6", **policy_examples()[1])]
        }
        webhooks = [
            [
                {
                    'id': '3',
                    'name': 'three',
                    'metadata': {},
                    'capability': {"version": "1", 'hash': 'xxx'}
                },
                {
                    'id': '4',
                    'name': 'four',
                    'metadata': {},
                    'capability': {"version": "1", 'hash': 'yyy'}
                }
            ],
            [
                {
                    'id': '5',
                    'name': 'five',
                    'metadata': {},
                    'capability': {"version": "1", 'hash': 'xxx'}
                },
                {
                    'id': '6',
                    'name': 'six',
                    'metadata': {},
                    'capability': {"version": "1", 'hash': 'yyy'}
                }
            ]
        ]
        webhooks_internal_links = [
            [[{"href": '/v1.0/11111/groups/one/policies/5/webhooks/3/', "rel": "self"},
              {"href": '/v1.0/execute/1/xxx/', "rel": "capability"}],
             [{"href": '/v1.0/11111/groups/one/policies/5/webhooks/4/', "rel": "self"},
              {"href": '/v1.0/execute/1/yyy/', "rel": "capability"}]],
            [[{"href": '/v1.0/11111/groups/one/policies/6/webhooks/5/', "rel": "self"},
              {"href": '/v1.0/execute/1/xxx/', "rel": "capability"}],
             [{"href": '/v1.0/11111/groups/one/policies/6/webhooks/6/', "rel": "self"},
              {"href": '/v1.0/execute/1/yyy/', "rel": "capability"}]]
        ]
        webhooks_links = [
            [{'href': '/v1.0/11111/groups/one/policies/5/webhooks/', 'rel': 'webhooks'}],
            [{'href': '/v1.0/11111/groups/one/policies/6/webhooks/', 'rel': 'webhooks'}]
        ]
        manifest['scalingPolicies'][0]['webhooks'] = webhooks[0]
        manifest['scalingPolicies'][1]['webhooks'] = webhooks[1]
        self.mock_group.view_manifest.return_value = defer.succeed(manifest)

        response_body = self.assert_status_code(
            200, endpoint="{0}?webhooks=true".format(self.endpoint), method="GET")
        resp = json.loads(response_body)
        validate(resp, rest_schemas.create_and_manifest_response)

        exp_policies = deepcopy(manifest['scalingPolicies'])
        for i in [0, 1]:
            exp_policies[i]['webhooks'] = deepcopy(webhooks[i])
            for j, webhook in enumerate(exp_policies[i]['webhooks']):
                exp_policies[i]['webhooks'][j]['links'] = webhooks_internal_links[i][j]
            exp_policies[i]['webhooks_links'] = webhooks_links[i]

        self.assertEqual(resp['group']['scalingPolicies'], exp_policies)

    def test_group_delete(self):
        """
        Deleting an existing group succeeds with a 204.
        """
        self.mock_group.update_config.return_value = defer.succeed(None)
        self.mock_group.delete_group.return_value = defer.succeed(None)

        response_body = self.assert_status_code(204, method="DELETE")
        self.assertEqual(response_body, "")
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.assertEqual(0, self.mock_group.update_config.call_count)
        self.mock_group.delete_group.assert_called_once_with()

    def test_group_delete_force(self):
        """
        Deleting a group with force sets min/max to zero and deletes it.
        """
        self.mock_controller = patch(self, 'otter.rest.groups.controller')

        self.mock_group.view_config.return_value = defer.succeed(
            {'name': 'group1', 'minEntities': '10', 'maxEntities': '1000'})
        self.mock_group.delete_group.return_value = defer.succeed(None)
        self.mock_group.update_config.return_value = defer.succeed(None)
        self.mock_controller.obey_config_change.return_value = defer.succeed(None)

        self.assert_status_code(
            204, endpoint="{0}?force=true".format(self.endpoint),
            method="DELETE")

        expected_config = {'maxEntities': 0, 'minEntities': 0, 'name': 'group1'}
        self.mock_group.update_config.assert_called_once_with(expected_config)
        self.mock_controller.obey_config_change.assert_called_once_with(
            mock.ANY, "transaction-id", expected_config, self.mock_group,
            self.mock_state, launch_config=None)
        self.mock_group.delete_group.assert_called_once_with()

    def test_group_delete_force_case_insensitive(self):
        """
        The 'true' specified in force is case insensitive.
        """
        self.mock_controller = patch(self, 'otter.rest.groups.controller')

        self.mock_group.view_config.return_value = defer.succeed({'name': 'group1'})
        self.mock_group.delete_group.return_value = defer.succeed(None)
        self.mock_group.update_config.return_value = defer.succeed(None)
        self.mock_controller.obey_config_change.return_value = defer.succeed(None)

        self.assert_status_code(
            204, endpoint="{0}?force=true".format(self.endpoint),
            method="DELETE")

        expected_config = {'maxEntities': 0, 'minEntities': 0, 'name': 'group1'}
        self.mock_group.update_config.assert_called_once_with(expected_config)
        self.mock_controller.obey_config_change.assert_called_once_with(
            mock.ANY, "transaction-id", expected_config, self.mock_group,
            self.mock_state, launch_config=None)
        self.mock_group.delete_group.assert_called_once_with()

    def test_group_delete_force_garbage_arg(self):
        """
        Providing an force argument other than 'true' causes an error.
        """
        self.mock_group.delete_group.return_value = defer.succeed(None)
        self.mock_group.update_config.return_value = defer.succeed(None)

        self.assert_status_code(
            400, endpoint="{0}?force=blah".format(self.endpoint),
            method="DELETE")

        self.assertEqual(0, self.mock_group.update_config.call_count)
        self.assertEqual(0, self.mock_group.delete_group.call_count)

    def test_group_delete_404(self):
        """
        Deleting a non-existant group fails with a 404.
        """
        self.mock_group.delete_group.return_value = defer.fail(
            NoSuchScalingGroupError('11111', '1'))

        response_body = self.assert_status_code(404, method="DELETE")
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.delete_group.assert_called_once_with()

        resp = json.loads(response_body)
        self.assertEqual(resp['error']['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_group_delete_403(self):
        """
        Deleting a non-empty group fails with a 403.
        """
        self.mock_group.delete_group.return_value = defer.fail(
            GroupNotEmptyError('11111', '1'))

        response_body = self.assert_status_code(403, method="DELETE")
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.delete_group.assert_called_once_with()

        resp = json.loads(response_body)
        self.assertEqual(resp['error']['type'], 'GroupNotEmptyError')
        self.flushLoggedErrors(GroupNotEmptyError)


class GroupStateTestCase(RestAPITestMixin, SynchronousTestCase):
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
        self.assertEqual(resp['error']['type'], 'NoSuchScalingGroupError')
        self.flushLoggedErrors(NoSuchScalingGroupError)

    @mock.patch('otter.rest.groups.format_state_dict')
    def test_view_state(self, mock_format):
        """
        Viewing the state of an existant group returns whatever the
        implementation's `view_state()` method returns, in string format, with
        the links reformatted so that they a list of dictionaries containing
        the attributes "id" and "links"
        """
        mock_format.return_value = {
            'active': [],
            'activeCapacity': 0,
            'pendingCapacity': 1,
            'desiredCapacity': 1,
            'paused': False,
            'id': 1,
            'links': [{'href': 'hey', 'rel': 'self'}]
        }
        self.mock_group.view_state.return_value = defer.succeed('group_state')
        response_body = self.assert_status_code(200, method="GET")
        resp = json.loads(response_body)

        # so long as all the servers are in the list of active servers, it's
        # fine.
        resp['group']['active'].sort()

        self.assertEqual(resp, {"group": mock_format.return_value})
        self.mock_store.get_scaling_group.assert_called_once_with(
            mock.ANY, '11111', 'one')
        self.mock_group.view_state.assert_called_once_with()
        mock_format.assert_called_once_with('group_state')


class GroupPauseTestCase(RestAPITestMixin, SynchronousTestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/pause/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/pause/"
    invalid_methods = ("DELETE", "GET", "PUT")

    def test_pause(self):
        """
        Pausing should call the controller's ``pause_scaling_group`` function
        """
        mock_pause = patch(
            self, 'otter.rest.groups.controller.pause_scaling_group',
            return_value=defer.succeed(None))
        response_body = self.assert_status_code(204, method="POST")
        self.assertEqual(response_body, "")

        mock_pause.assert_called_once_with(mock.ANY, 'transaction-id',
                                           self.mock_group)

    def test_pause_not_implemented(self):
        """
        Resume currently raises 501 not implemented
        """
        self.assert_status_code(501, method="POST")


class GroupResumeTestCase(RestAPITestMixin, SynchronousTestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/resume/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/resume/"
    invalid_methods = ("DELETE", "GET", "PUT")

    def test_resume(self):
        """
        Resume should call the controller's ``resume_scaling_group`` function
        """
        mock_resume = patch(
            self, 'otter.rest.groups.controller.resume_scaling_group',
            return_value=defer.succeed(None))
        response_body = self.assert_status_code(204, method="POST")
        self.assertEqual(response_body, "")

        mock_resume.assert_called_once_with(mock.ANY, 'transaction-id',
                                            self.mock_group)

    def test_resume_not_implemented(self):
        """
        Resume currently raises 501 not implemented
        """
        self.assert_status_code(501, method="POST")


class GroupServersTests(RestAPITestMixin, SynchronousTestCase):
    """
    Tests for ``/{tenantId}/groups/{groupId}/servers/`` endpoint
    """
    endpoint = "/v1.0/11111/groups/one/servers/"
    invalid_methods = ("POST", "PUT")

    def setUp(self):
        """
        Mock remove_server_from_group
        """
        super(GroupServersTests, self).setUp()
        self.mock_rsfg = patch(self, 'otter.rest.groups.remove_server_from_group',
                               return_value=None)
        self.patch(groups, "extract_bool_arg", self._extract_bool_arg)
        self._replace = self._purge = True

    def _extract_bool_arg(self, request, key, default):
        """
        A fake _extract_bool_arg, for testing.
        """
        self.assertTrue(isinstance(request, Request))
        self._request = request
        if key == "replace":
            self.assertTrue(default)
            return self._replace
        elif key == "purge":
            self.assertTrue(default)
            return self._purge
        else:  # pragma: no cover
            raise RuntimeError("unknown extract_bool_arg key: {}".format(key))

    def _check_remove_server_from_group_call(self, replace=True, purge=True):
        """
        Asserts that the call to :func:`remove_server_from_group` is correct.
        """
        self.mock_rsfg.assert_called_once_with(
            matches(IsBoundWith(system='otter.rest.groups.delete_server',
                                tenant_id='11111',
                                scaling_group_id='one',
                                server_id='s1',
                                transaction_id='transaction-id')),
            'transaction-id', 's1', replace, purge, self.mock_group, self.mock_state)

    def _test_server_delete(self, replace, purge):
        """
        A generic server deletion test.

        :param bool replace: Should the server be replaced?
        :param bool purge: Should the server be purged?
        :return: :data:`None`.
        """
        self._replace, self._purge = replace, purge
        body = self.assert_status_code(202, self.endpoint + 's1', "DELETE")
        self.assertEqual(body, "")
        self.assertEqual(self._request.uri, self.endpoint + 's1')
        self._check_remove_server_from_group_call(replace, purge)

    def test_server_purge_with_replace(self):
        """
        Servers can be purged and replaced.
        """
        self._test_server_delete(replace=True, purge=True)

    def test_server_purge_without_replace(self):
        """
        Servers can be purged without replacement.
        """
        self._test_server_delete(replace=False, purge=True)

    def test_server_removal_with_replace(self):
        """
        Servers can be removed from the group, without being removed from Nova,
        but with replacement.
        """
        self._test_server_delete(replace=True, purge=False)

    def test_server_removal_without_replace(self):
        """
        Servers can be removed from the group, without being removed from Nova,
        and without replacement.
        """
        self._test_server_delete(replace=False, purge=False)

    def test_server_delete_server_not_found(self):
        """
        404 error is returned when server is not found
        """
        self.mock_rsfg.return_value = defer.fail(ServerNotFoundError('t', 'g', 's'))
        body = self.assert_status_code(404, self.endpoint + 's1', "DELETE")
        self.assertIn('ServerNotFoundError', body)
        self.assertEqual(self._request.uri, self.endpoint + 's1')
        self._check_remove_server_from_group_call()

    def test_server_delete_size_error(self):
        """
        403 error is returned if deleting server will break min/max boundary
        """
        self.mock_rsfg.return_value = defer.fail(CannotDeleteServerBelowMinError('t', 'g', 's', 3))
        body = self.assert_status_code(403, self.endpoint + 's1', "DELETE")
        self.assertIn('CannotDeleteServerBelowMinError', body)
        self.assertEqual(self._request.uri, self.endpoint + 's1')
        self._check_remove_server_from_group_call()

    def test_get_servers_not_implemented(self):
        """
        GET /servers is not implemented
        """
        self.assert_status_code(501, method="GET")

    def test_get_server_id_not_implemented(self):
        """
        GET /servers/id is not implemented
        """
        self.assert_status_code(501, method="GET", endpoint=self.endpoint + 's1')
