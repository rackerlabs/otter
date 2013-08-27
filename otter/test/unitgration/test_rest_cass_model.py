"""
Integration-y tests for the REST interface interacting with the Cassandra model.

This is perhaps not the place for these tests to go.  Also, perhaps this should
instead be tested by spinning up an actually HTTP server (thus this test can
happen using the mock tap file).

But until a decision has been made for integration test infrastructure and
frameworks, this will do for now, as it is needed to verify that the rest unit
tests and Cassandra model unit tests do not lie.
"""

import json
import mock
import os

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from otter.json_schema.group_examples import (
    config, launch_server_config)
from otter.models.interface import (
    GroupState, NoSuchPolicyError, NoSuchScalingGroupError)
from otter.models.cass import CassScalingGroupCollection
from otter.rest.application import root, set_store

from otter.test.resources import OtterKeymaster

from otter.test.rest.request import path_only, request, RequestTestMixin
from otter.test.utils import LockMixin, patch
from otter.util.config import set_config_data


def _policy():
    return [
        {
            "name": "scale up by 10",
            "change": 10,
            "cooldown": 5,
            "type": "webhook"
        },
        {
            "name": 'scale down by 5.5 percent',
            "changePercent": -5.5,
            "cooldown": 6,
            "type": "webhook"
        },
        {
            "name": 'set number of servers to 10',
            "desiredCapacity": 10,
            "cooldown": 3,
            "type": "webhook"
        },
        {
            "name": 'scale down by 5 percent',
            "changePercent": -5,
            "cooldown": 6,
            "type": "webhook"
        },
        {
            "name": 'set number of servers to 20',
            "desiredCapacity": 20,
            "cooldown": 3,
            "type": "webhook"
        },
    ]

try:
    cassandra_host = os.environ.get('CASSANDRA_HOST', 'localhost')
    cassandra_port = int(os.environ.get('CASSANDRA_PORT', 9160))
    keymaster = OtterKeymaster(host=cassandra_host, port=cassandra_port)
except Exception as e:
    skip = "Cassandra unavailable: {0}".format(e)
else:
    keyspace = keymaster.get_keyspace()
    store = CassScalingGroupCollection(keyspace.client)


class CassStoreRestScalingGroupTestCase(TestCase, RequestTestMixin, LockMixin):
    """
    Test case for testing the REST API for the scaling group specific endpoints
    (not policies or webhooks) against the Cassandra model.
    """

    _launch_server_config = launch_server_config()[0]
    _policies = _policy()

    def setUp(self):
        """
        Set the Cassandra store, and also patch the controller
        """
        keyspace.resume()
        set_store(store)
        set_config_data({'url_root': 'http://127.0.0.1'})
        self.addCleanup(set_config_data, {})

        self.config = config()[0]
        self.config['minEntities'] = 0
        self.active_pending_etc = ({}, {}, 'date', {}, False)

        # patch both the config and the groups
        self.mock_controller = patch(self, 'otter.rest.configs.controller',
                                     spec=['obey_config_change'])
        patch(self, 'otter.rest.groups.controller', new=self.mock_controller)

        def _mock_obey_config_change(log, trans, config, group, state):
            return defer.succeed(GroupState(
                state.tenant_id, state.group_id, *self.active_pending_etc))

        self.mock_controller.obey_config_change.side_effect = _mock_obey_config_change

        self.lock = self.mock_lock()
        patch(self, 'otter.models.cass.BasicLock', return_value=self.lock)

    def tearDown(self):
        """
        Disconnect the client - it will reconnect as needed.  Better if this
        could be disconnected only once this particular module were done.
        """
        keyspace.dirtied()
        keyspace.pause()
        keyspace.reset(self.mktemp())

    def create_scaling_group(self):
        """
        Creates a scaling group and returns the path.
        """
        def _check_create_response(wrapper):
            # the body is probably verified by the unit tests - check the
            # header and status code
            self.assert_response(wrapper, 201, "Create failed.")
            # now make sure the Location header points to something good!
            return path_only(self.get_location_header(wrapper))

        request_body = {
            "groupConfiguration": self.config,
            "launchConfiguration": self._launch_server_config,
            "scalingPolicies": self._policies
        }
        deferred = request(
            root, 'POST', '/v1.0/11111/groups/', body=json.dumps(request_body))
        deferred.addCallback(_check_create_response)
        return deferred

    def create_and_view_scaling_group(self):
        """
        Creating a scaling group with a valid config returns with a 200 OK and
        a Location header pointing to the new scaling group.

        :return: the path to the new scaling group resource
        """
        def _check_policies_created(wrapper):
            self.assert_response(wrapper, 200)
            response = json.loads(wrapper.content)
            self.assertEqual(len(response["policies"]), len(self._policies))

        def _check_creation_worked(path):
            # TODO: check manifest and state as well
            d = defer.gatherResults([
                request(root, 'GET', path + 'policies/').addCallback(
                    _check_policies_created),
                self.assert_state(path, self.config['minEntities'], False)])

            # no matter what, just return the path
            return d.addCallback(lambda _: path)

        deferred = self.create_scaling_group()
        deferred.addCallback(_check_creation_worked)
        return deferred

    def assert_state(self, path, entities, paused):
        """
        Assert that the state has the specified number of total entities and
        is or is not paused, as specified.

        :return: deferred that fires with None
        """
        def _check_state(wrapper):
            self.assertEqual(wrapper.response.code, 200)
            response = json.loads(wrapper.content)
            self.assertEqual(response['group']['paused'], paused)
            self.assertEqual(response['group']['desiredCapacity'], entities)

        return request(root, 'GET', path + 'state/').addCallback(_check_state)

    @defer.inlineCallbacks
    def delete_and_view_scaling_group(self, path):
        """
        Deleting a scaling group returns with a 204 no content.  The next
        attempt to view the scaling group should return a 404 not found.
        """
        wrapper = yield request(root, 'DELETE', path)
        self.assert_response(wrapper, 204, "Delete failed.")
        self.assertEqual(wrapper.content, "")

        # now try to view policies
        # TODO: view state and manifest too, once they have been implemented
        wrapper = yield request(root, 'GET', path + 'policies/')
        self.assert_response(wrapper, 404, "Deleted group still there.")

        # flush any logged errors
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def assert_number_of_scaling_groups(self, number):
        """
        Asserts that there are ``number`` number of scaling groups
        """
        def _check_number(wrapper):
            self.assert_response(wrapper, 200)
            response = json.loads(wrapper.content)
            self.assertEqual(len(response["groups"]), number)

        d = request(root, 'GET', '/v1.0/11111/groups/')
        return d.addCallback(_check_number)

    @defer.inlineCallbacks
    def test_crd_scaling_group(self):
        """
        Start with no scaling groups.  Create one, make sure it's listed, then
        delete it and make sure it's no longer listed.
        """
        # start with no scaling groups
        yield self.assert_number_of_scaling_groups(0)
        path = yield self.create_and_view_scaling_group()

        # there should now be one scaling group
        yield self.assert_number_of_scaling_groups(1)
        yield self.delete_and_view_scaling_group(path)

        # there should be no scaling groups now
        yield self.assert_number_of_scaling_groups(0)

    @defer.inlineCallbacks
    def test_update_launch_config(self):
        """
        Editing the launch config of a scaling group with a valid launch config
        returns with a 204 no content.  The next attempt to view the launch
        config should return the new launch config.
        """
        path = yield self.create_scaling_group()
        launch_path = path + 'launch/'
        edited_launch = launch_server_config()[1]

        wrapper = yield request(root, 'PUT',
                                launch_path, body=json.dumps(edited_launch))
        self.assert_response(wrapper, 204, "Edit launch config failed.")
        self.assertEqual(wrapper.content, "")

        # now try to view again - the config should be the edited config
        wrapper = yield request(root, 'GET', launch_path)
        self.assert_response(wrapper, 200)
        self.assertEqual(json.loads(wrapper.content),
                         {'launchConfiguration': edited_launch})

    @defer.inlineCallbacks
    def test_update_config(self):
        """
        Editing the config of a scaling group to one with a higher min returns
        204 with no content.  The state is updated to reflect existing at least
        the min number of pending + current
        """
        path = yield self.create_and_view_scaling_group()
        config_path = path + 'config/'

        self.config['minEntities'] = 2
        self.config['maxEntities'] = 25
        self.config['metadata'] = {}
        self.active_pending_etc = ({}, {'1': {}, '2': {}}, 'date', {}, False)

        wrapper = yield request(root, 'PUT', config_path,
                                body=json.dumps(self.config))
        self.assert_response(wrapper, 204, "Edit config failed")
        self.assertEqual(wrapper.content, "")

        yield self.assert_state(path, 2, False)

    @defer.inlineCallbacks
    def test_create_scaling_group_with_min_entities(self):
        """
        Create a scaling group with >0 min entities calls obey config changes
        """
        self.config['minEntities'] = 2
        self.active_pending_etc = ({}, {'1': {}, '2': {}}, 'date', {}, False)

        path = yield self.create_scaling_group()
        yield self.assert_state(path, 2, False)


class CassStoreRestScalingPolicyTestCase(TestCase, RequestTestMixin, LockMixin):
    """
    Test case for testing the REST API for the scaling policy specific endpoints
    (but not webhooks) against the mock model.

    As above, this could be made a base case instead... yadda yadda.
    """
    tenant_id = '11111'

    def setUp(self):
        """
        Set up a silverberg client
        """
        keyspace.resume()
        set_store(store)  # ensure it's the cassandra store

        set_config_data({'url_root': 'http://127.0.0.1'})
        self.addCleanup(set_config_data, {})

        self._config = config()[0]
        self._launch = launch_server_config()[0]

        self.mock_controller = patch(self, 'otter.rest.policies.controller')

        self.lock = self.mock_lock()
        patch(self, 'otter.models.cass.BasicLock', return_value=self.lock)

        def _set_group_id(manifest):
            self.group_id = manifest['id']
            self.policies_url = (
                '/v1.0/{tenant}/groups/{group}/policies/'.format(
                    tenant=self.tenant_id, group=self.group_id))
            self.mock_controller.maybe_execute_scaling_policy.return_value = defer.succeed(
                GroupState(self.tenant_id, self.group_id, {}, {}, 'date', {}, False))

        mock_log = mock.MagicMock()
        d = store.create_scaling_group(mock_log, self.tenant_id,
                                       self._config, self._launch)
        d.addCallback(_set_group_id)
        return d

    def tearDown(self):
        """
        Disconnect the client - it will reconnect as needed.  Better if this
        could be disconnected only once this particular module were done.
        """
        keyspace.dirtied()
        keyspace.pause()
        keyspace.reset(self.mktemp())

    def assert_number_of_scaling_policies(self, number):
        """
        Asserts that there are ``number`` number of scaling policies
        """
        def _check_number(wrapper):
            self.assert_response(wrapper, 200)
            response = json.loads(wrapper.content)
            self.assertEqual(len(response["policies"]), number)

        d = request(root, 'GET', self.policies_url)
        return d.addCallback(_check_number)

    def create_and_view_scaling_policies(self):
        """
        Creating valid scaling policies returns with a 200 OK, a Location
        header pointing to the list of all scaling policies, and a response
        containing a list of the newly created scaling policy resources only.

        :return: a list self links to the new scaling policies (not guaranteed
            to be in any consistent order)
        """
        request_body = _policy()[:-1]  # however many of them there are minus one

        def _verify_create_response(wrapper):
            self.assert_response(wrapper, 201, "Create policies failed.")
            response = json.loads(wrapper.content)

            self.assertEqual(len(request_body), len(response["policies"]))

            # this iterates over the response policies, checks to see that each
            # have 'id' and 'links' keys, and then checks to see that the rest
            # of the response policy is in the original set of policies to be
            #created
            for pol in response["policies"]:
                original_pol = pol.copy()
                for key in ('id', 'links'):
                    self.assertIn(key, pol)
                    del original_pol[key]
                self.assertIn(original_pol, request_body)

            # now make sure the Location header points to the list policies
            #header
            location = path_only(self.get_location_header(wrapper))
            self.assertEqual(location, self.policies_url)

            links = [path_only(link["href"])
                     for link in pol["links"] if link["rel"] == "self"
                     for pol in response["policies"]]
            return links

        d = request(root, 'POST', self.policies_url,
                    body=json.dumps(request_body))
        return d.addCallback(_verify_create_response)

    @defer.inlineCallbacks
    def update_and_view_scaling_policy(self, path):
        """
        Updating a scaling policy returns with a 204 no content.  When viewing
        the policy again, it should contain the updated version.
        """
        request_body = _policy()[-1]  # the one that was not created

        wrapper = yield request(root, 'PUT', path,
                                body=json.dumps(request_body))
        self.assert_response(wrapper, 204, "Update policy failed.")
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = yield request(root, 'GET', path)
        self.assert_response(wrapper, 200)

        response = json.loads(wrapper.content)
        updated = response['policy']

        self.assertIn('id', updated)
        self.assertIn('links', updated)
        self.assertIn(
            path, [path_only(link["href"]) for link in updated["links"]])

        del updated['id']
        del updated['links']

        self.assertEqual(updated, request_body)

    @defer.inlineCallbacks
    def delete_and_view_scaling_policy(self, path):
        """
        Deleting a scaling policy returns with a 204 no content.  The next
        attempt to view the scaling policy should return a 404 not found.
        """
        wrapper = yield request(root, 'DELETE', path)
        self.assert_response(wrapper, 204, "Delete policy failed.")
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = yield request(root, 'GET', path)
        self.assert_response(wrapper, 404, "Deleted policy still there.")

        # flush any logged errors
        self.flushLoggedErrors(NoSuchPolicyError)

    @defer.inlineCallbacks
    def test_crud_scaling_policies(self):
        """
        Start with no policies.  Create some, make sure they're listed,
        create some more because we want to verify that creation response
        contains only the ones that were created.  Then update one of them,
        check changes. Then delete one of them and make sure it's no longer
        listed.
        """
        # start with no scaling groups
        yield self.assert_number_of_scaling_policies(0)
        first_policies = yield self.create_and_view_scaling_policies()

        # create more scaling policies, to check the creation response
        yield self.assert_number_of_scaling_policies(len(first_policies))
        second_policies = yield self.create_and_view_scaling_policies()
        len_total_policies = len(first_policies) + len(second_policies)
        yield self.assert_number_of_scaling_policies(len_total_policies)

        # update scaling policy, and there should still be the same number of
        # policies after the update
        yield self.update_and_view_scaling_policy(first_policies[0])
        yield self.assert_number_of_scaling_policies(len_total_policies)

        # delete a scaling policy - there should be one fewer scaling policy
        yield self.delete_and_view_scaling_policy(second_policies[0])
        yield self.assert_number_of_scaling_policies(len_total_policies - 1)

    @defer.inlineCallbacks
    def test_execute_scaling_policy_success(self):
        """
        Executing a scaling policy should result in a 202.
        """
        yield self.assert_number_of_scaling_policies(0)
        first_policies = yield self.create_and_view_scaling_policies()

        yield self.assert_number_of_scaling_policies(len(first_policies))

        wrapper = yield request(root, 'POST', first_policies[0] + 'execute/')
        self.assertEqual(wrapper.response.code, 202,
                         "Execute failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "{}")

    @defer.inlineCallbacks
    def test_execute_scaling_policy_failed(self):
        """
        Executing a non-existant scaling policy should result in a 404.
        """
        self.mock_controller.maybe_execute_scaling_policy.return_value = defer.fail(
            NoSuchPolicyError('11111', '1', '2'))

        wrapper = yield request(root, 'POST', self.policies_url + '1/execute/')
        self.assertEqual(wrapper.response.code, 404,
                         "Execute did not fail as expected: {0}".format(wrapper.content))

        self.flushLoggedErrors(NoSuchPolicyError)
