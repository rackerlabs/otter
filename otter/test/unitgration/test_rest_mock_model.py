"""
Integration-y tests for the REST interface interacting with the mock model.

This is perhaps not the place for these tests to go.  Also, perhaps this should
instead be tested by spinning up an actually HTTP server (thus this test can
happen using the mock tap file).

But until a decision has been made for integration test infrastructure and
frameworks, this will do for now, as it is needed to verify that the rest unit
tests and mock model unit tests do not lie.
"""

import json
import mock
from urlparse import urlsplit

from twisted.trial.unittest import TestCase
from twisted.internet import defer

from otter.json_schema.group_examples import config, launch_server_config, policy
from otter.models.interface import (
    GroupState, NoSuchPolicyError, NoSuchScalingGroupError, NoSuchWebhookError)
from otter.models.mock import MockScalingGroupCollection
from otter.rest.application import Otter
from otter.supervisor import set_supervisor

from otter.test.rest.request import request
from otter.test.utils import patch

from otter.util.config import set_config_data


def _strip_base_url(url):
    return urlsplit(url)[2]


class MockStoreRestScalingGroupTestCase(TestCase):
    """
    Test case for testing the REST API for the scaling group specific endpoints
    (not policies or webhooks) against the mock model.

    This could be made a base case instead, and different implementations of
    the model interfaces should be tested using a subclass of this base case.

    The store should be cleared between every test case and the test fixture
    reloaded at the start of every test case.

    The plan for the case of a DB is that an object can be created that starts
    up a DB, knows how to clear it, load particular fixtures, etc.  Each test
    case can be passed to a function in this instance that loads a fixture
    before every test method (or not), and cleans up after every test calling
    the test case's `addCleanup` method.  Then, the object will shut down the
    DB process when `trial` finishes its run.

    That way the same DB object can be used for other integration tests as well
    (not just this test case), and so the DB only needs to be started once.

    In the case of in-memory stores, fixtures can be loaded and duplicated.
    """

    def setUp(self):
        """
        Replace the store every time with a clean one.
        """
        store = MockScalingGroupCollection()
        self.root = Otter(store).app.resource()
        set_config_data({'url_root': 'http://127.0.0.1'})
        self.addCleanup(set_config_data, {})

        self.config = config()[1]
        self.config['minEntities'] = 0
        self.active_pending_etc = ({}, {}, 'date', {}, False)

        # patch both the config and the groups
        self.mock_controller = patch(self, 'otter.rest.configs.controller',
                                     spec=['obey_config_change'])
        patch(self, 'otter.rest.groups.controller', new=self.mock_controller)

        # Patch supervisor
        supervisor = mock.Mock(spec=['validate_launch_config'])
        supervisor.validate_launch_config.return_value = defer.succeed(None)
        set_supervisor(supervisor)

        def _mock_obey_config_change(log, trans, config, group, state):
            return defer.succeed(GroupState(
                state.tenant_id, state.group_id, state.group_name, *self.active_pending_etc))

        self.mock_controller.obey_config_change.side_effect = _mock_obey_config_change

    def tearDown(self):
        """
        reset supervisor
        """
        set_supervisor(None)

    def create_and_view_scaling_group(self):
        """
        Creating a scaling group with a valid config returns with a 200 OK and
        a Location header pointing to the new scaling group.

        :return: the path to the new scaling group resource
        """
        request_body = {
            "groupConfiguration": self.config,
            "launchConfiguration": launch_server_config()[0]
        }
        wrapper = self.successResultOf(request(
            self.root, 'POST', '/v1.0/11111/groups/', body=json.dumps(request_body)))

        self.assertEqual(wrapper.response.code, 201,
                         "Create failed: {0}".format(wrapper.content))
        response = json.loads(wrapper.content)
        for key in request_body:
            self.assertEqual(response["group"][key], request_body[key])
        for key in ("id", "links"):
            self.assertTrue(key in response["group"])

        headers = wrapper.response.headers.getRawHeaders('Location')
        self.assertTrue(headers is not None)
        self.assertEqual(1, len(headers))

        # now make sure the Location header points to something good!
        path = _strip_base_url(headers[0])

        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 200, path)

        response = json.loads(wrapper.content)
        self.assertEqual(response["group"]['groupConfiguration'], self.config)
        self.assertEqual(response["group"]['launchConfiguration'],
                         launch_server_config()[0])

        # make sure the created group has enough pending entities, and is
        # not paused
        wrapper = self.successResultOf(
            request(self.root, 'GET', path + 'state/'))
        self.assertEqual(wrapper.response.code, 200)

        response = json.loads(wrapper.content)
        self.assertTrue(not response["group"]['paused'])

        return path

    def delete_and_view_scaling_group(self, path):
        """
        Deleting a scaling group returns with a 204 no content.  The next
        attempt to view the scaling group should return a 404 not found.
        """
        wrapper = self.successResultOf(request(self.root, 'DELETE', path))
        self.assertEqual(wrapper.response.code, 204,
                         "Delete failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 404)
        wrapper = self.successResultOf(
            request(self.root, 'GET', path + 'state/'))
        self.assertEqual(wrapper.response.code, 404)

        # flush any logged errors
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def assert_number_of_scaling_groups(self, number):
        """
        Asserts that there are ``number`` number of scaling groups
        """
        wrapper = self.successResultOf(
            request(self.root, 'GET', '/v1.0/11111/groups/'))
        self.assertEqual(200, wrapper.response.code)

        response = json.loads(wrapper.content)
        self.assertEqual(len(response["groups"]), number)

    def test_crd_scaling_group(self):
        """
        Start with no scaling groups.  Create one, make sure it's listed, then
        delete it and make sure it's no longer listed.
        """
        # start with no scaling groups
        self.assert_number_of_scaling_groups(0)
        path = self.create_and_view_scaling_group()

        # there should still be one scaling group
        self.assert_number_of_scaling_groups(1)
        self.delete_and_view_scaling_group(path)

        # there should be no scaling groups now
        self.assert_number_of_scaling_groups(0)

    def test_ru_launch_config(self):
        """
        Editing the launch config of a scaling group with a valid launch config
        returns with a 204 no content.  The next attempt to view the launch
        config should return the new launch config.
        """
        # make sure there is a scaling group
        path = self.create_and_view_scaling_group() + 'launch/'
        edited_launch = launch_server_config()[1]

        wrapper = self.successResultOf(
            request(self.root, 'PUT', path, body=json.dumps(edited_launch)))

        self.assertEqual(wrapper.response.code, 204,
                         "Edit failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view again - the config should be the edited config
        wrapper = self.successResultOf(
            request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 200)
        self.assertEqual(json.loads(wrapper.content),
                         {'launchConfiguration': edited_launch})


class MockStoreRestScalingPolicyTestCase(TestCase):
    """
    Test case for testing the REST API for the scaling policy specific endpoints
    (but not webhooks) against the mock model.

    As above, this could be made a base case instead... yadda yadda.
    """
    tenant_id = '11111'

    def setUp(self):
        """
        Replace the store every time with a clean one.
        """
        store = MockScalingGroupCollection()
        self.mock_log = mock.MagicMock()
        manifest = self.successResultOf(
            store.create_scaling_group(self.mock_log, self.tenant_id, config()[0],
                                       launch_server_config()[0]))
        self.group_id = manifest['state'].group_id
        self.group_name = 'name'

        self.policies_url = '/v1.0/{tenant}/groups/{group}/policies/'.format(
            tenant=self.tenant_id, group=self.group_id)

        controller_patcher = mock.patch('otter.rest.policies.controller')
        self.mock_controller = controller_patcher.start()
        self.mock_controller.maybe_execute_scaling_policy.return_value = defer.succeed(
            GroupState(self.tenant_id, self.group_id, self.group_name, {}, {}, 'date', {}, False))
        self.addCleanup(controller_patcher.stop)

        self.root = Otter(store).app.resource()

        set_config_data({'url_root': 'http://127.0.0.1'})
        self.addCleanup(set_config_data, {})

    def assert_number_of_scaling_policies(self, number):
        """
        Asserts that there are ``number`` number of scaling policies
        """
        wrapper = self.successResultOf(
            request(self.root, 'GET', self.policies_url))
        self.assertEqual(200, wrapper.response.code)

        response = json.loads(wrapper.content)
        self.assertEqual(len(response["policies"]), number)

    def create_and_view_scaling_policies(self):
        """
        Creating valid scaling policies returns with a 200 OK, a Location
        header pointing to the list of all scaling policies, and a response
        containing a list of the newly created scaling policy resources only.

        :return: a list self links to the new scaling policies (not guaranteed
            to be in any consistent order)
        """
        request_body = policy()[:-1]  # however many of them there are minus one
        wrapper = self.successResultOf(request(
            self.root, 'POST', self.policies_url, body=json.dumps(request_body)))

        self.assertEqual(wrapper.response.code, 201,
                         "Create failed: {0}".format(wrapper.content))
        response = json.loads(wrapper.content)

        self.assertEqual(len(request_body), len(response["policies"]))

        # this iterates over the response policies, checks to see that each have
        # 'id' and 'links' keys, and then checks to see that the rest of the
        # response policy is in the original set of policies to be created
        for pol in response["policies"]:
            original_pol = pol.copy()
            for key in ('id', 'links'):
                self.assertIn(key, pol)
                del original_pol[key]
            self.assertIn(original_pol, request_body)

        headers = wrapper.response.headers.getRawHeaders('Location')
        self.assertTrue(headers is not None)
        self.assertEqual(1, len(headers))

        # now make sure the Location header points to the list policies header
        self.assertEqual(_strip_base_url(headers[0]), self.policies_url)

        links = [_strip_base_url(link["href"])
                 for link in pol["links"] if link["rel"] == "self"
                 for pol in response["policies"]]
        return links

    def update_and_view_scaling_policy(self, path):
        """
        Updating a scaling policy returns with a 204 no content.  When viewing
        the policy again, it should contain the updated version.
        """
        request_body = policy()[-1]  # the one that was not created
        wrapper = self.successResultOf(
            request(self.root, 'PUT', path, body=json.dumps(request_body)))
        self.assertEqual(wrapper.response.code, 204,
                         "Update failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 200)

        response = json.loads(wrapper.content)
        updated = response['policy']

        self.assertIn('id', updated)
        self.assertIn('links', updated)
        self.assertIn(
            path, [_strip_base_url(link["href"]) for link in updated["links"]])

        del updated['id']
        del updated['links']

        self.assertEqual(updated, request_body)

    def delete_and_view_scaling_policy(self, path):
        """
        Deleting a scaling policy returns with a 204 no content.  The next
        attempt to view the scaling policy should return a 404 not found.
        """
        wrapper = self.successResultOf(request(self.root, 'DELETE', path))
        self.assertEqual(wrapper.response.code, 204,
                         "Delete failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 404)

        # flush any logged errors
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_crud_scaling_policies(self):
        """
        Start with no policies.  Create some, make sure they're listed,
        create some more because we want to verify that creation response
        contains only the ones that were created.  Then update one of them,
        check changes. Then delete one of them and make sure it's no longer
        listed.
        """
        # start with no scaling groups
        self.assert_number_of_scaling_policies(0)
        first_policies = self.create_and_view_scaling_policies()

        # create more scaling policies, to check the creation response
        self.assert_number_of_scaling_policies(len(first_policies))
        second_policies = self.create_and_view_scaling_policies()
        len_total_policies = len(first_policies) + len(second_policies)
        self.assert_number_of_scaling_policies(len_total_policies)

        # update scaling policy, and there should still be the same number of
        # policies after the update
        self.update_and_view_scaling_policy(first_policies[0])
        self.assert_number_of_scaling_policies(len_total_policies)

        # delete a scaling policy - there should be one fewer scaling policy
        self.delete_and_view_scaling_policy(second_policies[0])
        self.assert_number_of_scaling_policies(len_total_policies - 1)

    def test_execute_scaling_policy_success(self):
        """
        Executing a scaling policy should result in a 202.
        """
        self.assert_number_of_scaling_policies(0)
        first_policies = self.create_and_view_scaling_policies()

        self.assert_number_of_scaling_policies(len(first_policies))

        wrapper = self.successResultOf(
            request(self.root, 'POST', first_policies[0] + 'execute/'))
        self.assertEqual(wrapper.response.code, 202,
                         "Execute failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "{}")

    def test_execute_scaling_policy_failed(self):
        """
        Executing a non-existant scaling policy should result in a 404.
        """

        self.mock_controller.maybe_execute_scaling_policy.return_value = defer.fail(
            NoSuchPolicyError('11111', '1', '2'))

        wrapper = self.successResultOf(
            request(self.root, 'POST', self.policies_url + '1/execute/'))
        self.assertEqual(wrapper.response.code, 404,
                         "Execute did not fail as expected: {0}".format(wrapper.content))

        self.flushLoggedErrors(NoSuchPolicyError)


class MockStoreRestWebhooksTestCase(TestCase):
    """
    Test case for testing the REST API for the webhook specific endpoints
    against the mock model.

    As above, this could be made a base case instead... yadda yadda.
    """
    tenant_id = '11111'

    def setUp(self):
        """
        Replace the store every time with a clean one.
        """
        self.mock_log = mock.MagicMock()
        store = MockScalingGroupCollection()
        manifest = self.successResultOf(
            store.create_scaling_group(self.mock_log, self.tenant_id,
                                       config()[0],
                                       launch_server_config()[0]))
        self.group_id = manifest['state'].group_id
        group = store.get_scaling_group(self.mock_log,
                                        self.tenant_id, self.group_id)
        self.policy_id = self.successResultOf(
            group.create_policies([{
                "name": 'set number of servers to 10',
                "change": 10,
                "cooldown": 3,
                "type": "webhook"
            }])).keys()[0]

        self.webhooks_url = (
            '/v1.0/{tenant}/groups/{group}/policies/{policy}/webhooks/'.format(
                tenant=self.tenant_id, group=self.group_id,
                policy=self.policy_id))

        self.mock_controller = patch(self, 'otter.rest.webhooks.controller')

        def _mock_maybe_execute(log, trans, group, state, policy_id):
            return defer.succeed(state)

        self.mock_controller.maybe_execute_scaling_policy.side_effect = _mock_maybe_execute

        self.root = Otter(store).app.resource()

        set_config_data({'url_root': 'http://127.0.0.1'})
        self.addCleanup(set_config_data, {})

    def assert_number_of_webhooks(self, number):
        """
        Asserts that there are ``number`` number of scaling policies
        """
        wrapper = self.successResultOf(
            request(self.root, 'GET', self.webhooks_url))
        self.assertEqual(200, wrapper.response.code)

        response = json.loads(wrapper.content)
        self.assertEqual(len(response["webhooks"]), number)

    def create_and_view_webhooks(self):
        """
        Creating valid webhooks returns with a 200 OK, a Location header
        pointing to the list of all webhooks, and a response containing a list
        of the newly created webhook resources only.

        :return: a list self links to the new webhooks (not guaranteed
            to be in any consistent order)
        """
        request_body = [
            {'name': 'first', 'metadata': {'notes': 'first webhook'}},
            {'name': 'second', 'metadata': {'notes': 'second webhook'}}
        ]
        wrapper = self.successResultOf(request(
            self.root, 'POST', self.webhooks_url, body=json.dumps(request_body)))

        self.assertEqual(wrapper.response.code, 201,
                         "Create failed: {0}".format(wrapper.content))
        response = json.loads(wrapper.content)

        self.assertEqual(len(request_body), len(response["webhooks"]))

        # this iterates over the webhooks, checks to see that each have
        # 'id' and 'links' keys, makes sure that there is an extra link
        # containing the capability URL, and then checks to see that the
        # rest of the responce is in the original set of webhooks to be created
        for webhook in response["webhooks"]:
            keys = webhook.keys()
            keys.sort()
            self.assertEqual(['id', 'links', 'metadata', 'name'], keys)
            self.assertIn(
                {'metadata': webhook['metadata'], 'name': webhook['name']},
                request_body)
            self.assertIn('capability',
                          [link_obj['rel'] for link_obj in webhook['links']])

        headers = wrapper.response.headers.getRawHeaders('Location')
        self.assertTrue(headers is not None)
        self.assertEqual(1, len(headers))

        # now make sure the Location header points to the list webhooks header
        self.assertEqual(_strip_base_url(headers[0]), self.webhooks_url)

        links = [_strip_base_url(link["href"])
                 for link in webhook["links"] if link["rel"] == "self"
                 for webhook in response["webhooks"]]
        return links

    def update_and_view_webhook(self, path):
        """
        Updating a webhook returns with a 204 no content.  When viewing
        the webhook again, it should contain the updated version.
        """
        request_body = {'name': 'updated_webhook', 'metadata': {'foo': 'bar'}}
        wrapper = self.successResultOf(
            request(self.root, 'PUT', path, body=json.dumps(request_body)))
        self.assertEqual(wrapper.response.code, 204,
                         "Update failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 200)

        response = json.loads(wrapper.content)
        updated = response['webhook']

        self.assertIn('id', updated)
        self.assertIn('links', updated)
        for link in updated["links"]:
            if link['rel'] == 'self':
                self.assertIn(_strip_base_url(link["href"]), path)
            else:
                self.assertEqual(link['rel'], 'capability')
                self.assertIn('/v1.0/execute/1/', link["href"])

        del updated['id']
        del updated['links']

        self.assertEqual(updated, {'name': 'updated_webhook', 'metadata': {'foo': 'bar'}})

    def delete_and_view_webhook(self, path):
        """
        Deleting a webhook returns with a 204 no content.  The next attempt to
        view the webhook should return a 404 not found.
        """
        wrapper = self.successResultOf(request(self.root, 'DELETE', path))
        self.assertEqual(wrapper.response.code, 204,
                         "Delete failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.successResultOf(request(self.root, 'GET', path))
        self.assertEqual(wrapper.response.code, 404)

        # flush any logged errors
        self.flushLoggedErrors(NoSuchWebhookError)

    def test_crud_webhooks(self):
        """
        Start with no policies.  Create some, make sure they're listed,
        create some more because we want to verify that creation response
        contains only the ones that were created.  Then update one of them,
        check changes. Then delete one of them and make sure it's no longer
        listed.
        """
        # start with no webhooks
        self.assert_number_of_webhooks(0)
        first_webhooks = self.create_and_view_webhooks()

        # create more webhooks, to check the creation response
        self.assert_number_of_webhooks(2)
        self.create_and_view_webhooks()
        self.assert_number_of_webhooks(4)

        # update webhook, and there should still be the same number of
        # webhook after the update
        self.update_and_view_webhook(first_webhooks[0])
        self.assert_number_of_webhooks(4)

        # delete webhook - there should be one fewer webhook
        self.delete_and_view_webhook(first_webhooks[0])
        self.assert_number_of_webhooks(3)

    def test_execute_webhook_by_hash(self):
        """
        Executing a webhook should look up the policy by hash and attempt
        to execute that policy.
        """
        self.assert_number_of_webhooks(0)
        first_webhooks = self.create_and_view_webhooks()

        wrapper = self.successResultOf(request(self.root, 'GET', first_webhooks[0]))
        webhook = json.loads(wrapper.content)['webhook']
        links = {link['rel']: link['href'] for link in webhook['links']}
        cap_path = _strip_base_url(links['capability'])

        wrapper = self.successResultOf(request(self.root, 'POST', cap_path))
        self.assertEqual(wrapper.response.code, 202)

    def test_execute_non_existant_webhook_by_hash(self):
        """
        Executing a webhook that doesn't exist should still return a 202.
        """
        self.assert_number_of_webhooks(0)

        wrapper = self.successResultOf(
            request(self.root, 'POST', '/v1.0/execute/1/1/'))
        self.assertEqual(wrapper.response.code, 202)
