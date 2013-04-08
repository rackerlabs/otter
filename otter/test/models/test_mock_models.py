"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.json_schema import group_examples
from otter.models.mock import (
    generate_entity_links, MockScalingGroup, MockScalingGroupCollection)
from otter.models.interface import (NoSuchScalingGroupError,
                                    NoSuchPolicyError, NoSuchWebhookError,
                                    UnrecognizedCapabilityError)

from otter.test.models.test_interface import (
    IScalingGroupStateProviderMixin,
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin)


class GenerateEntityLinksTestCase(TestCase):
    """
    Tests for :func:`generate_entity_links`
    """

    def test_default_format_for_one_link(self):
        """
        Link can be generated from just the tenant ID and entity ID.
        """
        links = generate_entity_links("1", ["1"])
        href = "http://dfw.servers.api.rackspacecloud.com/v2/1/servers/1"
        self.assertEqual(links, {
            "1": [
                {
                    "rel": "self",
                    "href": href
                }
            ]
        })

    def test_region_version_options_for_one_link(self):
        """
        Link can also be generated for a particular region and api version and
        entity type
        """
        links = generate_entity_links("1", ["1"], region="ord",
                                      api_version="1.0",
                                      entity_type="loadbalancers")
        href = ("http://ord.loadbalancers.api.rackspacecloud.com/"
                "v1.0/1/loadbalancers/1")
        self.assertEqual(links, {
            "1": [
                {
                    "rel": "self",
                    "href": href
                }
            ]
        })

    def test_creates_links_for_each_entity_id(self):
        """
        If 5 ids are passed in, 5 links are returned
        """
        links = generate_entity_links("1", [str(i) for i in range(5)])
        self.assertEqual(len(links), 5)


class MockScalingGroupStateTestCase(IScalingGroupStateProviderMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`'s ``IScalingGroupState`` interface
    implementation.
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.tenant_id = '11111'
        self.mock_log = mock.MagicMock()

        # config, launch config, etc. policies don't matter
        self.state = MockScalingGroup(
            self.mock_log, self.tenant_id, 1,
            {'config': {}, 'launch': {}, 'policies': {}})

    def test_state(self):
        """
        Test the normal use case..  update an empty group with a job,
        move the server to fully operational.
        """
        jobs = {"job1": {"created": "2012-12-25 00:00:00-06:39Z"}}
        d = self.state.update_jobs({}, jobs, "trans1", "pol1", "2012-12-25 00:00:00-06:39Z")
        self.assert_deferred_succeeded(d)
        d = self.state.view_state()
        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, {'active': {},
                                  'paused': False,
                                  'groupTouched': '2012-12-25 00:00:00-06:39Z',
                                  'pending': {'job1': {'created': '2012-12-25 00:00:00-06:39Z'}},
                                  'policyTouched': {'pol1': '2012-12-25 00:00:00-06:39Z'}})
        d = self.state.add_server(result, "foo", "frrr", "uri", "job1", '2012-12-25 00:00:00-06:39Z')
        self.assert_deferred_succeeded(d)
        d = self.state.view_state()
        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, {'active': {'frrr': {'name': 'foo',
                                                      'instanceURL': 'uri',
                                                      'created': '2012-12-25 00:00:00-06:39Z'}},
                                  'paused': False,
                                  'groupTouched': '2012-12-25 00:00:00-06:39Z',
                                  'pending': {},
                                  'policyTouched': {'pol1': '2012-12-25 00:00:00-06:39Z'}})

    def test_state_bad_job_id(self):
        """
        Test that if we try to pass in a bad job ID it continues
        """
        d = self.state.add_server({}, "foo", "frrr", "uri", "job1", '2012-12-25 00:00:00-06:39Z')
        self.assert_deferred_failed(d, Exception)
        d = self.state.view_state()
        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, {'active': {},
                                  'paused': False,
                                  'groupTouched': None,
                                  'pending': {},
                                  'policyTouched': {}})

    def test_state_bad_server(self):
        """
        Test that if we try to pass in a bad server it continues
        """
        jobs = {"job1": {"created": "2012-12-25 00:00:00-06:39Z"},
                "job2": {"created": "2012-12-25 00:00:00-06:39Z"}}
        d = self.state.update_jobs({}, jobs, "trans1", "pol1", "2012-12-25 00:00:00-06:39Z")
        self.assert_deferred_succeeded(d)
        d = self.state.view_state()
        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, {'active': {},
                                  'paused': False,
                                  'groupTouched': '2012-12-25 00:00:00-06:39Z',
                                  'pending': {'job1': {'created': '2012-12-25 00:00:00-06:39Z'},
                                              'job2': {'created': '2012-12-25 00:00:00-06:39Z'}},
                                  'policyTouched': {'pol1': '2012-12-25 00:00:00-06:39Z'}})
        d = self.state.add_server(result, "foo", "frrr", "uri", "job1", '2012-12-25 00:00:00-06:39Z')
        self.assert_deferred_succeeded(d)
        d = self.state.add_server(result, "foo", "frrr", "uri", "job2", '2012-12-25 00:00:00-06:39Z')
        self.assert_deferred_failed(d, Exception)
        d = self.state.view_state()
        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, {'active': {'frrr': {'name': 'foo',
                                                      'instanceURL': 'uri',
                                                      'created': '2012-12-25 00:00:00-06:39Z'}},
                                  'paused': False,
                                  'groupTouched': '2012-12-25 00:00:00-06:39Z',
                                  'pending': {'job2': {'created': '2012-12-25 00:00:00-06:39Z'}},
                                  'policyTouched': {'pol1': '2012-12-25 00:00:00-06:39Z'}})

    def test_pause(self):
        """
        Tests that pause sets the state to paused, returns None, and pausing
        an already paused group does not raise an error.
        """
        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertFalse(result['paused'], "sanity check")

        self.assertIsNone(self.assert_deferred_succeeded(self.state.pause()))
        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertTrue(result['paused'], "Pausing should set paused to True")

        self.assertIsNone(self.assert_deferred_succeeded(self.state.pause()))
        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertTrue(result['paused'], "Pausing again should not fail")

    def test_resume(self):
        """
        Tests that resume sets the state to unpaused, returns None, and resuming
        an already resumed group does not raise an error.
        """
        self.state.paused = True

        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertTrue(result['paused'], "sanity check")

        self.assertIsNone(self.assert_deferred_succeeded(self.state.resume()))
        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertFalse(result['paused'], "Resuming should set paused to False")

        self.assertIsNone(self.assert_deferred_succeeded(self.state.resume()))
        result = self.assert_deferred_succeeded(self.state.view_state())
        self.assertFalse(result['paused'], "Resuming again should not fail")


class MockScalingGroupTestCase(IScalingGroupProviderMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.tenant_id = '11111'
        self.mock_log = mock.MagicMock()
        self.config = {
            'name': 'aname',
            'cooldown': 0,
            'minEntities': 0
        }
        # this is the config with all the default vals
        self.output_config = {
            'name': 'aname',
            'cooldown': 0,
            'minEntities': 0,
            'maxEntities': None,
            'metadata': {}
        }
        self.launch_config = {
            "type": "launch_server",
            "args": {"server": {"these are": "some args"}}
        }
        self.policies = group_examples.policy()[:1]
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, 1,
            {'config': self.config, 'launch': self.launch_config,
             'policies': self.policies})

    def test_view_manifest_has_all_info(self):
        """
        View manifest should return a dictionary that conforms to the JSON
        schema
        """
        result = self.validate_view_manifest_return_value()
        self.assertEqual(result['groupConfiguration'], self.output_config)
        self.assertEqual(result['launchConfiguration'], self.launch_config)
        self.assertEqual(result['scalingPolicies'].values(), self.policies)

    def test_default_view_config_has_all_info(self):
        """
        View should return a dictionary that conforms to the JSON schema (has
        all parameters even though only a few were passed in)
        """
        result = self.validate_view_config_return_value()
        self.assertEqual(result, self.output_config)

    def test_view_launch_config_returns_what_it_was_created_with(self):
        """
        The view config that is returned by the MockScalingGroup is the same
        one it was created with.  There is currently no validation for what
        goes in and hence what goes out, so just check if they are the same.
        """
        result = self.assert_deferred_succeeded(self.group.view_launch_config())
        self.assertEqual(result, self.launch_config)

    def test_view_state_returns_valid_scheme_when_empty(self):
        """
        ``view_state`` returns all the state information stored in the
        MockScalingGroup as the required keys
        """
        result = self.assert_deferred_succeeded(self.group.view_state())
        self.assertEquals(result, {
            'active': {},
            'pending': {},
            'paused': False,
            'groupTouched': None,
            'policyTouched': {}
        })

    def test_update_config_overwrites_existing_data(self):
        """
        Passing in a dict only overwrites the existing dict unless the
        `partial_update` flag is passed as True
        """
        expected = {
            'cooldown': 1000,
            'metadata': {'UPDATED': 'UPDATED'},
            'minEntities': 10,
            'maxEntities': 15,
            'name': 'UPDATED'
        }
        self.assert_deferred_succeeded(self.group.update_config(expected))
        result = self.validate_view_config_return_value()
        self.assertEqual(result, expected)

    def test_update_config_does_not_overwrite_existing_non_provided_keys(self):
        """
        If certain keys are not provided in the update dictionary and the
        `partial_update` flag is provided as True, the keys that are not
        provided are not overwritten.
        """
        self.assert_deferred_succeeded(self.group.update_config(
            {}, partial_update=True))
        result = self.validate_view_config_return_value()

        # because the returned value has the defaults filled in even if they
        # were not provided
        expected = dict(self.config)
        expected['maxEntities'] = None
        expected['metadata'] = {}
        self.assertEqual(result, expected)

    def test_update_config_does_not_change_launch_config(self):
        """
        When the config is updated, the launch config doesn't change.
        """
        self.assert_deferred_succeeded(self.group.update_config({
            'cooldown': 1000,
            'metadata': {'UPDATED': 'UPDATED'},
            'minEntities': 10,
            'maxEntities': 15,
            'name': 'UPDATED'
        }))
        self.assertEqual(
            self.assert_deferred_succeeded(self.group.view_launch_config()),
            self.launch_config)

    def test_update_launch_config_overwrites_existing_data(self):
        """
        There is no partial update for the launch config.  Whatever
        `update_launch_config` is called with is what will be saved.
        """
        updated = {
            "type": "launch_server",
            "args": {"server": {"here are": "new args"}}
        }
        self.assert_deferred_succeeded(self.group.update_launch_config(updated))
        result = self.assert_deferred_succeeded(self.group.view_launch_config())
        self.assertEqual(result, updated)

    def test_update_launch_config_does_not_change_config(self):
        """
        When the launch_config is updated, the config doesn't change.
        """
        self.assert_deferred_succeeded(self.group.update_launch_config({
            "type": "launch_server",
            "args": {"server": {"here are": "new args"}}
        }))
        self.assertEqual(
            self.assert_deferred_succeeded(self.group.view_config()),
            self.output_config)

    def test_create_new_scaling_policies(self):
        """
        Adding new policies to the scaling group returns a dictionary of
        scaling policies mapped to their ids
        """
        create_response = self.validate_create_policies_return_value([
            {
                "name": "scale down by 20",
                "change": -20,
                "cooldown": 300,
                "type": "webhook"
            },
            {
                "name": 'scale down 10 percent',
                "changePercent": -10,
                "cooldown": 200,
                "type": "webhook"
            }
        ])
        list_result = self.assert_deferred_succeeded(self.group.list_policies())
        self.assertGreater(len(list_result), len(create_response))
        for key, value in create_response.iteritems():
            self.assertEqual(list_result[key], value)

    def test_list_empty_policies(self):
        """
        If there are no policies, list policies conforms to the schema and
        also is an empty dictionary
        """
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, 1,
            {'config': self.config, 'launch': self.launch_config,
             'policies': None})
        self.assertEqual(self.validate_list_policies_return_value(), {})

    def test_list_all_policies(self):
        """
        List existing policies returns a dictionary of the policy mapped to the
        ID
        """
        policies_dict = self.validate_list_policies_return_value()
        self.assertEqual(len(policies_dict), len(self.policies))
        policies = policies_dict.values()
        for a_policy in self.policies:
            self.assertIn(a_policy, policies)

    def test_get_policy_succeeds(self):
        """
        Try to get a policy by looking up all available UUIDs, and getting one.
        """
        policy_list = self.assert_deferred_succeeded(self.group.list_policies())
        uuid = policy_list.keys()[0]
        value = policy_list.values()[0]
        result = self.assert_deferred_succeeded(self.group.get_policy(uuid))
        self.assertEqual(value, result)

    def test_get_nonexistent_policy_fails(self):
        """
        Get a policy that doesn't exist returns :class:`NoSuchPolicyError`
        """
        uuid = "Otters are so cute!"
        deferred = self.group.get_policy(uuid)
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_delete_policy_succeeds(self):
        """
        Delete a policy, check that it is actually deleted.
        """
        policy_list = self.assert_deferred_succeeded(self.group.list_policies())
        uuid = policy_list.keys()[0]
        self.assert_deferred_succeeded(self.group.delete_policy(uuid))
        result = self.assert_deferred_succeeded(self.group.list_policies())
        self.assertNotIn(uuid, result)
        self.assertEqual({}, result)

    def test_delete_nonexistent_policy_fails(self):
        """
        Delete a policy that doesn't exist. Should return with NoSuchPolicyError
        """
        deferred = self.group.delete_policy("puppies")
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_delete_policy_removes_webhooks(self):
        """
        Deleting an existing policy removes its associated webhooks too
        """
        self.group.policies = {"2": {}}
        self.group.webhooks = {"2": {}}
        self.assert_deferred_succeeded(self.group.delete_policy("2"))
        self.assertNotIn("2", self.group.webhooks)

    def test_update_policy_succeeds(self):
        """
        Get a UUID and attempt to update the policy.
        """
        policy_list = self.assert_deferred_succeeded(self.group.list_policies())
        uuid = policy_list.keys()[0]
        update_data = {
            "name": "Otters are not good pets",
            "change": 1234,
            "cooldown": 555
        }
        self.assert_deferred_succeeded(self.group.update_policy(uuid, update_data))
        result = self.assert_deferred_succeeded(
            self.group.get_policy(uuid))
        self.assertEqual(update_data, result)

    def test_update_nonexistent_policy_fails(self):
        """
        Attempt to update a nonexistant policy.
        """
        update_data = {
            "name": "puppies are good pets",
            "change": 1234,
            "cooldown": 555
        }
        deferred = self.group.update_policy("puppies", update_data)
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_list_webhooks_nonexistant_policy_fails(self):
        """
        Listing webhooks on a policy that doesn't exist fails with a
        :class:`NoSuchPolicyError`
        """
        deferred = self.group.list_webhooks("otter-stacking")
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_list_empty_webhooks(self):
        """
        If there are no webhooks, an empty dictionary is returned when
        ``list_webhooks`` is called
        """
        policy_list = self.assert_deferred_succeeded(self.group.list_policies())
        uuid = policy_list.keys()[0]
        result = self.validate_list_webhooks_return_value(uuid)
        self.assertEqual(result, {})

    def test_list_webhooks_succeeds(self):
        """
        If there are webhooks for a particular policy, listing webhooks returns
        a dictionary for all of them
        """
        policy_list = self.assert_deferred_succeeded(self.group.list_policies())
        uuid = policy_list.keys()[0]
        webhooks = {
            '10': self.sample_webhook_data,
            '11': self.sample_webhook_data
        }
        self.group.webhooks = {uuid: webhooks}
        result = self.validate_list_webhooks_return_value(uuid)
        self.assertEqual(result, webhooks)

    def test_create_webhooks_nonexistant_policy_fails(self):
        """
        Creating webhooks on a policy that doesn't exist fails with a
        :class:`NoSuchPolicyError`
        """
        deferred = self.group.create_webhooks("otter-stacking", [{}])
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    @mock.patch('otter.models.mock.generate_capability',
                return_value=("ver", "hash"))
    def test_create_webhooks_succeed(self, fake_random):
        """
        Adding new webhooks to the scaling policy returns a dictionary of
        scaling webhooks mapped to their ids
        """
        self.group.policies = {'2': {}}
        # have a fake webhook already
        self.group.webhooks = {
            '2': {
                'fake': {
                    'capability': {
                        'hash': 'fake',
                        'ver': '1'
                    },
                    'name': 'meh',
                    'metadata': {}
                }
            }
        }

        # create two webhooks, both empty
        creation = self.validate_create_webhooks_return_value(
            '2', [{'name': 'one'}, {'name': 'two'}])
        self.assertEqual(len(creation), 2)
        for name in ('one', 'two'):
            self.assertIn({
                'name': name,
                'metadata': {},
                'capability': {
                    'hash': 'hash',
                    'version': 'ver'
                },
            }, creation.values())

        # listing should return 3
        listing = self.assert_deferred_succeeded(self.group.list_webhooks('2'))
        self.assertGreater(len(listing), len(creation))

    def test_get_webhook_nonexistent_policy_fails(self):
        """
        Updating a webhook of a nonexistant policy fails with a
        :class:`NoSuchPolicyError`.
        """
        deferred = self.group.get_webhook("puppies", "1")
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_get_nonexistant_webhook_fails(self):
        """
        Getting a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        self.group.webhooks = {'2': {}}
        deferred = self.group.get_webhook("2", "1")
        self.assert_deferred_failed(deferred, NoSuchWebhookError)

    def test_get_webhook_updates_existing_dictionary(self):
        """
        Get webhook updates the data that's already there but doesn't
        delete the capability url.
        """
        expected_webhook = {
            'name': 'original',
            'capability': {'hash': 'xxx', 'version': '3'},
            'metadata': {'key': 'value'}
        }
        self.group.policies = {'2': {}}
        self.group.webhooks = {'2': {'3': expected_webhook}}
        deferred = self.group.get_webhook("2", "3")
        self.assertEqual(self.assert_deferred_succeeded(deferred),
                         expected_webhook)

    def test_update_webhook_nonexistent_policy_fails(self):
        """
        Updating a webhook of a nonexistant policy fails with a
        :class:`NoSuchPolicyError`.
        """
        deferred = self.group.update_webhook("puppies", "1", {'name': 'fake'})
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_update_nonexistant_webhook_fails(self):
        """
        Updating a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        deferred = self.group.update_webhook("2", "1", {'name': 'fake'})
        self.assert_deferred_failed(deferred, NoSuchWebhookError)

    def test_update_webhook_updates_existing_dictionary(self):
        """
        Updating webhook updates the data that's already there but doesn't
        delete the capability url.
        """
        self.group.policies = {'2': {}}
        self.group.webhooks = {
            '2': {
                '3': {
                    'name': 'original',
                    'capability': {'hash': 'xxx', 'version': '3'},
                    'metadata': {'key': 'value'}
                }
            }
        }
        deferred = self.group.update_webhook("2", "3", {
            'name': 'updated',
            'metadata': {'key2': 'value2'}
        })
        self.assertIsNone(self.assert_deferred_succeeded(deferred))
        self.assertEqual(self.group.webhooks, {
            '2': {
                '3': {
                    'name': 'updated',
                    'capability': {'hash': 'xxx', 'version': '3'},
                    'metadata': {'key2': 'value2'}
                }
            }
        })

    def test_update_webhook_without_metadata_erases_metadata(self):
        """
        Updating a webhook and not providing metadata erases metadata that's
        already there.
        """
        self.group.policies = {'2': {}}
        self.group.webhooks = {
            '2': {
                '3': {
                    'name': 'original',
                    'capability': {'hash': 'xxx', 'version': '3'},
                    'metadata': {'key': 'value'}
                }
            }
        }
        deferred = self.group.update_webhook("2", "3", {'name': 'updated'})
        self.assertIsNone(self.assert_deferred_succeeded(deferred))
        self.assertEqual(self.group.webhooks, {
            '2': {
                '3': {
                    'name': 'updated',
                    'capability': {'hash': 'xxx', 'version': '3'},
                    'metadata': {}
                }
            }
        })

    def test_delete_webhook_nonexistent_policy_fails(self):
        """
        Deleting a webhook of a nonexistant policy fails with a
        :class:`NoSuchPolicyError`.
        """
        deferred = self.group.delete_webhook("puppies", "1")
        self.assert_deferred_failed(deferred, NoSuchPolicyError)

    def test_delete_nonexistant_webhook_fails(self):
        """
        Deleting a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        deferred = self.group.delete_webhook("2", "1")
        self.assert_deferred_failed(deferred, NoSuchWebhookError)

    def test_delete_webhook_succeeds(self):
        """
        If deleting a webhook succeeds, webhook is removed from store.
        """
        self.group.policies = {'2': {}}
        self.group.webhooks = {
            '2': {
                '3': {
                    'name': 'original',
                    'capability': {'hash': 'xxx', 'version': '3'},
                    'metadata': {'key': 'value'}
                }
            }
        }
        deferred = self.group.delete_webhook("2", "3")
        self.assertIsNone(self.assert_deferred_succeeded(deferred))
        self.assertEqual(self.group.webhooks, {'2': {}})


class MockScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`MockScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.collection = MockScalingGroupCollection()
        self.tenant_id = 'goo1234'
        self.config = {
            'name': 'blah',
            'cooldown': 600,
            'minEntities': 0,
            'maxEntities': 10,
            'metadata': {}
        }
        self.mock_log = mock.MagicMock()

    def test_list_scaling_groups_is_empty_if_new_tenant_id(self):
        """
        Listing all scaling groups for a tenant id, with no scaling groups
        because they are a new tenant id, returns an empty list
        """
        self.assertEqual(self.validate_list_return_value(self.mock_log, self.
                         tenant_id), [],
                         "Should start off with zero groups for tenant")

    @mock.patch('otter.models.mock.MockScalingGroup', wraps=MockScalingGroup)
    def test_create_group_with_config_and_list_scaling_groups(self, mock_sgrp):
        """
        Listing a scaling group returns a mapping of scaling group uuid to
        scaling group model, and adding another scaling group increases the
        number of scaling groups in the collection.  These are tested together
        since testing list involves putting scaling groups in the collection
        (create), and testing creation involves enumerating the collection
        (list)

        Creation of a scaling group with a 'config' parameter creates a
        scaling group with the specified configuration.
        """
        launch = {"launch": "config"}
        policies = group_examples.policy()
        self.assertEqual(self.validate_list_return_value(
                         self.mock_log, self.
                         tenant_id), [],
                         "Should start off with zero groups")
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, launch, policies))

        result = self.validate_list_return_value(self.mock_log, self.tenant_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].uuid, uuid, "Group not added to collection")

        mock_sgrp.assert_called_once_with(
            mock.ANY, self.tenant_id, uuid,
            {'config': self.config, 'launch': launch, 'policies': policies})

    @mock.patch('otter.models.mock.MockScalingGroup', wraps=MockScalingGroup)
    def test_create_group_with_no_policies(self, mock_sgrp):
        """
        Creating a scaling group with all arguments except policies passes None
        as policies to the MockScalingGroup.
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, {}))  # empty launch for testing

        mock_sgrp.assert_called_once_with(
            mock.ANY, self.tenant_id, uuid,
            {'config': self.config, 'launch': {}, 'policies': None})

    def test_delete_removes_a_scaling_group(self):
        """
        Deleting a valid scaling group decreases the number of scaling groups
        in the collection
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, {}))  # empty launch for testing

        result = self.validate_list_return_value(self.mock_log, self.tenant_id)
        self.assertEqual(len(result), 1, "Group not added correctly")

        self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.mock_log, self.tenant_id, uuid))

        result = self.validate_list_return_value(self.mock_log, self.tenant_id)
        self.assertEqual(result, [], "Group not deleted from collection")

    def test_delete_scaling_group_fails_if_scaling_group_does_not_exist(self):
        """
        Deleting a scaling group that doesn't exist raises a
        :class:`NoSuchScalingGroupError` exception
        """
        deferred = self.collection.delete_scaling_group(self.mock_log, self.tenant_id, 1)
        self.assert_deferred_failed(deferred, NoSuchScalingGroupError)

    @mock.patch('otter.models.mock.generate_capability',
                return_value=("ver", "hash"))
    def test_webhook_info_by_hash(self, mock_generation):
        """
        Tests that we can get info for a webhook given a capability token.
        """
        launch = {"launch": "config"}
        policy = {
            "name": "scale up by 10",
            "change": 10,
            "cooldown": 5
        }
        self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, launch, {}))

        result = self.validate_list_return_value(self.mock_log, self.tenant_id)
        group = result[0]

        pol_rec = self.assert_deferred_succeeded(group.create_policies([policy]))

        pol_uuid = pol_rec.keys()[0]

        self.assert_deferred_succeeded(group.create_webhooks(pol_uuid, [{}]))

        deferred = self.collection.webhook_info_by_hash(self.mock_log, 'hash')
        webhook_info = self.assert_deferred_succeeded(deferred)
        self.assertEqual(webhook_info, (self.tenant_id, group.uuid, pol_uuid))

    @mock.patch('otter.models.mock.generate_capability',
                return_value=("ver", "hash"))
    def test_webhook_info_no_hash(self, mock_generation):
        """
        Tests that, given a bad capability token, we error out.
        """
        launch = {"launch": "config"}
        policy = {
            "name": "scale up by 10",
            "change": 10,
            "cooldown": 5
        }
        self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, launch, {}))

        result = self.validate_list_return_value(self.mock_log, self.tenant_id)
        group = result[0]

        pol_rec = self.assert_deferred_succeeded(group.create_policies([policy]))

        pol_uuid = pol_rec.keys()[0]

        self.assert_deferred_succeeded(group.create_webhooks(pol_uuid, [{}]))

        deferred = self.collection.webhook_info_by_hash(self.mock_log, 'weasel')
        self.assert_deferred_failed(deferred, UnrecognizedCapabilityError)

    @mock.patch('otter.models.mock.generate_capability',
                return_value=("ver", "hash"))
    def _call_all_methods_on_group(self, group_id, mock_generation):
        """
        Gets a group, asserts that it's a MockScalingGroup, and runs all of its
        calls and returns their deferreds as a list
        """
        group = self.validate_get_return_value(self.mock_log, self.tenant_id,
                                               group_id)
        self.assertTrue(isinstance(group, MockScalingGroup),
                        "group is {0!r}".format(group))

        group.active_entities = ["1"]
        group.policies = {'1': {}, '2': {}, '3': {}}
        group.webhooks = {'1': {}, '2': {}, '3': {'3x': {}}}

        return [
            group.view_config(),
            group.view_launch_config(),
            group.view_state(),
            group.update_config({
                'name': '1',
                'minEntities': 0,
                'cooldown': 0,
                'maxEntities': None,
                'metadata': {}
            }),
            group.update_launch_config({
                "type": "launch_server",
                "args": {
                    "server": {
                        "flavorRef": 2,
                        "name": "worker",
                        "imageRef": "a09e7493-7429-41e1-8d3f-384d7ece09c0"
                    }
                }
            }),
            group.list_policies(),
            group.create_policies([]),
            group.get_policy('2'),
            group.update_policy('2', {}),
            group.delete_policy('1'),
            group.list_webhooks('2'),
            group.create_webhooks('2', [{}, {}]),
            group.get_webhook('3', '3x'),
            group.update_webhook('3', '3x', {'name': 'hat'}),
            group.delete_webhook('3', '3x')
        ]

    def test_get_scaling_group_returns_mock_scaling_group(self):
        """
        Getting valid scaling group returns a MockScalingGroup whose methods
        work.
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, {}))  # empty launch for testing

        succeeded_deferreds = self._call_all_methods_on_group(uuid)
        for deferred in succeeded_deferreds:
            self.assert_deferred_succeeded(deferred)

    def test_get_scaling_group_works_but_methods_do_not(self):
        """
        Getting a scaling group that doesn't exist returns a MockScalingGropu
        whose methods will raise :class:`NoSuchScalingGroupError` exceptions.
        """
        failed_deferreds = self._call_all_methods_on_group("1")

        for deferred in failed_deferreds:
            self.assert_deferred_failed(deferred, NoSuchScalingGroupError)
