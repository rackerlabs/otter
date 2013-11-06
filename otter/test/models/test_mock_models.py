"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.json_schema import group_examples
from otter.models.mock import (
    generate_entity_links, MockScalingGroup, MockScalingGroupCollection,
    MockAdmin)
from otter.models.interface import (
    GroupState, GroupNotEmptyError, NoSuchScalingGroupError,
    NoSuchPolicyError, NoSuchWebhookError, UnrecognizedCapabilityError)

from otter.test.models.test_interface import (
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin,
    IScalingScheduleCollectionProviderMixin)

from otter.test.utils import mock_log, patch


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


class MockScalingGroupTestCase(IScalingGroupProviderMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.tenant_id = '11111'
        self.group_id = '1'
        self.mock_log = mock.MagicMock()
        self.collection = mock.MagicMock(spec=[], data={self.tenant_id: {}})

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
        self.launch_config = group_examples.launch_server_config()[0]
        self.policies = group_examples.policy()[:1]
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, self.group_id, self.collection,
            {'config': self.config, 'launch': self.launch_config,
             'policies': self.policies})

        self.collection.data[self.tenant_id]['1'] = self.group

        self.counter = 0

        def generate_uuid():
            self.counter += 1
            return self.counter

        self.mock_uuid = patch(self, 'otter.models.mock.uuid4',
                               side_effect=generate_uuid)

    def test_view_manifest_has_all_info(self):
        """
        View manifest should return a dictionary that conforms to the JSON
        schema
        """
        result = self.validate_view_manifest_return_value()
        self.assertEqual(result['groupConfiguration'], self.output_config)
        self.assertEqual(result['launchConfiguration'], self.launch_config)
        self.assertEqual(result['id'], '1')
        self.assertEqual(
            result['state'], GroupState(self.tenant_id, '1', '', {}, {}, None, {}, False)
        )

        policies = result['scalingPolicies']
        for policy in policies:
            del policy['id']
            assert policy in self.policies

        self.assertEqual(len(policies), len(self.policies))

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
        result = self.successResultOf(self.group.view_launch_config())
        self.assertEqual(result, self.launch_config)

    def test_view_state_returns_empty_state(self):
        """
        ``view_state`` a group state with empty info
        """
        result = self.successResultOf(self.group.view_state())
        self.assertEqual(result, GroupState(self.tenant_id, '1', '', {}, {},
                                            None, {}, False))

    def test_modify_state(self):
        """
        ``modify_state`` saves the new state returned by the function if the
        tenant ids and group ids match
        """
        new_state = GroupState(self.tenant_id, self.group_id, 'aname', {1: {}}, {},
                               'date', {}, True)

        def modifier(group, state):
            return new_state

        self.group.modify_state(modifier)
        self.assertEqual(self.group.state, new_state)

    def test_modify_state_fails_if_tenant_ids_do_not_match(self):
        """
        ``modify_state`` does not save the state that the modifier returns if
        the tenant IDs do not match
        """
        def modifier(group, state):
            return GroupState('tid', self.group_id, 'aname', {}, {}, 'date', {}, True)

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(AssertionError))

    def test_modify_state_fails_if_group_ids_do_not_match(self):
        """
        ``modify_state`` does not save the state that the modifier returns if
        the tenant IDs do not match
        """
        def modifier(group, state):
            return GroupState(self.tenant_id, 'meh', 'aname', {}, {}, 'date', {}, True)

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(AssertionError))

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
        self.successResultOf(self.group.update_config(expected))
        result = self.validate_view_config_return_value()
        self.assertEqual(result, expected)

    def test_update_config_does_not_overwrite_existing_non_provided_keys(self):
        """
        If certain keys are not provided in the update dictionary and the
        `partial_update` flag is provided as True, the keys that are not
        provided are not overwritten.
        """
        self.successResultOf(self.group.update_config(
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
        self.successResultOf(self.group.update_config({
            'cooldown': 1000,
            'metadata': {'UPDATED': 'UPDATED'},
            'minEntities': 10,
            'maxEntities': 15,
            'name': 'UPDATED'
        }))
        self.assertEqual(
            self.successResultOf(self.group.view_launch_config()),
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
        self.successResultOf(self.group.update_launch_config(updated))
        result = self.successResultOf(self.group.view_launch_config())
        self.assertEqual(result, updated)

    def test_update_launch_config_does_not_change_config(self):
        """
        When the launch_config is updated, the config doesn't change.
        """
        self.successResultOf(self.group.update_launch_config({
            "type": "launch_server",
            "args": {"server": {"here are": "new args"}}
        }))
        self.assertEqual(
            self.successResultOf(self.group.view_config()),
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
                "type": "webhook",
            },
            {
                "name": 'scale down 10 percent',
                "changePercent": -10,
                "cooldown": 200,
                "type": "webhook",
            }
        ])
        list_result = self.successResultOf(self.group.list_policies())
        self.assertGreater(len(list_result), len(create_response))
        for item in create_response:
            self.assertIn(item, list_result)

    def test_delete_group_removes_self_from_collection_if_state_empty(self):
        """
        Deleting a scaling group succeeds if there are no active and pending
        entities/jobs.
        """
        self.assertEqual(len(self.collection.data[self.group.tenant_id]), 1)
        d = self.group.delete_group()
        self.assertEqual(None, self.successResultOf(d))
        self.assertEqual(len(self.collection.data[self.group.tenant_id]), 0)

    def test_delete_scaling_group_fails_if_scaling_group_not_empty(self):
        """
        Deleting a scaling group that has active or pending jobs errbacks with
        a :class:`GroupNotEmptyError`
        """
        self.group.state.active = {'1': {}}
        self.failureResultOf(self.group.delete_group(), GroupNotEmptyError)
        self.assertEqual(len(self.collection.data[self.group.tenant_id]), 1)

    def test_list_empty_policies(self):
        """
        If there are no policies, list policies conforms to the schema and
        also is an empty dictionary
        """
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, '1', self.collection,
            {'config': self.config, 'launch': self.launch_config,
             'policies': None})
        self.assertEqual(self.validate_list_policies_return_value(), [])

    def test_list_all_policies(self):
        """
        List existing policies returns a dictionary of the policy mapped to the
        ID
        """
        policies = self.validate_list_policies_return_value()
        self.assertEqual(len(policies), len(self.policies))
        for policy in policies:
            del policy['id']

        for a_policy in self.policies:
            self.assertIn(a_policy, policies)

    def test_list_policies_limits_number_of_policies(self):
        """
        Listing all policies limits the number of policies by the limit
        specified
        """
        self.policies = group_examples.policy()[:3]
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, self.group_id, self.collection,
            {'config': self.config, 'launch': self.launch_config,
             'policies': self.policies})

        policies = self.validate_list_policies_return_value(limit=2)
        self.assertEqual([p['id'] for p in policies], ['1', '2'])

    def test_list_policies_offsets_by_marker(self):
        """
        Listing all policies will offset the list by the last seen parameter
        """
        self.policies = group_examples.policy()[:3]
        self.group = MockScalingGroup(
            self.mock_log, self.tenant_id, self.group_id, self.collection,
            {'config': self.config, 'launch': self.launch_config,
             'policies': self.policies})

        policies = self.validate_list_policies_return_value(limit=2, marker='1')
        self.assertEqual([p['id'] for p in policies], ['2', '3'])

    def test_get_policy_succeeds(self):
        """
        Try to get a policy by looking up all available UUIDs, and getting one.
        """
        policy_list = self.successResultOf(self.group.list_policies())
        value = policy_list[0]
        uuid = value.pop('id')
        result = self.successResultOf(self.group.get_policy(uuid))
        self.assertEqual(value, result)

    def test_get_nonexistent_policy_fails(self):
        """
        Get a policy that doesn't exist returns :class:`NoSuchPolicyError`
        """
        uuid = "Otters are so cute!"
        deferred = self.group.get_policy(uuid)
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_delete_policy_succeeds(self):
        """
        Delete a policy, check that it is actually deleted.
        """
        policy_list = self.successResultOf(self.group.list_policies())
        uuid = policy_list[0]['id']
        self.successResultOf(self.group.delete_policy(uuid))

        result = self.successResultOf(self.group.list_policies())
        ids = [policy['id'] for policy in result]
        self.assertNotIn(uuid, ids)
        self.assertEqual([], result)

    def test_delete_nonexistent_policy_fails(self):
        """
        Delete a policy that doesn't exist. Should return with NoSuchPolicyError
        """
        deferred = self.group.delete_policy("puppies")
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_delete_policy_removes_webhooks(self):
        """
        Deleting an existing policy removes its associated webhooks too
        """
        self.group.policies = {"2": {}}
        self.group.webhooks = {"2": {}}
        self.successResultOf(self.group.delete_policy("2"))
        self.assertNotIn("2", self.group.webhooks)

    def test_update_policy_succeeds(self):
        """
        Get a UUID and attempt to update the policy.
        """
        policy_list = self.successResultOf(self.group.list_policies())
        uuid = policy_list[0]['id']
        update_data = {
            "name": "Otters are not good pets",
            "change": 1234,
            "cooldown": 555,
            "type": "webhook"
        }
        self.successResultOf(self.group.update_policy(uuid, update_data))
        result = self.successResultOf(
            self.group.get_policy(uuid))
        self.assertEqual(update_data, result)

    def test_update_nonexistent_policy_fails(self):
        """
        Attempt to update a nonexistant policy.
        """
        update_data = {
            "name": "puppies are good pets",
            "change": 1234,
            "cooldown": 555,
            "type": "webhook"
        }
        deferred = self.group.update_policy("puppies", update_data)
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_list_webhooks_nonexistant_policy_fails(self):
        """
        Listing webhooks on a policy that doesn't exist fails with a
        :class:`NoSuchPolicyError`
        """
        deferred = self.group.list_webhooks("otter-stacking")
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_list_empty_webhooks(self):
        """
        If there are no webhooks, an empty dictionary is returned when
        ``list_webhooks`` is called
        """
        policy_list = self.successResultOf(self.group.list_policies())
        uuid = policy_list[0]['id']
        result = self.validate_list_webhooks_return_value(uuid)
        self.assertEqual(result, [])

    def test_list_webhooks_succeeds(self):
        """
        If there are webhooks for a particular policy, listing webhooks returns
        a dictionary for all of them
        """
        policy_list = self.successResultOf(self.group.list_policies())
        uuid = policy_list[0]['id']
        webhooks = {
            '10': self.sample_webhook_data,
            '11': self.sample_webhook_data
        }
        self.group.webhooks = {uuid: webhooks}
        result = self.validate_list_webhooks_return_value(uuid)
        self.assertEqual(result, [
            dict(id='10', **self.sample_webhook_data),
            dict(id='11', **self.sample_webhook_data)
        ])

    def test_list_webhooks_limits_number_of_webhooks(self):
        """
        Listing all webhooks limits the number of webhooks by the limit
        specified
        """
        policy_id = self.group.policies.keys()[0]
        self.group.webhooks = {
            policy_id: {
                '10': self.sample_webhook_data,
                '11': self.sample_webhook_data
            }
        }
        result = self.validate_list_webhooks_return_value(policy_id, limit=1)
        self.assertEqual(result, [
            dict(id='10', **self.sample_webhook_data)
        ])

    def test_list_webooks_offsets_by_marker(self):
        """
        Listing all webhooks will offset the list by the last seen parameter
        """
        policy_id = self.group.policies.keys()[0]
        self.group.webhooks = {
            policy_id: {
                '10': self.sample_webhook_data,
                '11': self.sample_webhook_data
            }
        }
        result = self.validate_list_webhooks_return_value(
            policy_id, limit=2, marker='10')
        self.assertEqual(result, [
            dict(id='11', **self.sample_webhook_data)
        ])

    def test_create_webhooks_nonexistant_policy_fails(self):
        """
        Creating webhooks on a policy that doesn't exist fails with a
        :class:`NoSuchPolicyError`
        """
        deferred = self.group.create_webhooks("otter-stacking", [{}])
        self.failureResultOf(deferred, NoSuchPolicyError)

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
        for item in creation:
            self.assertIn('id', item)
            del item['id']

        self.assertEqual(creation, [
            {
                'name': name,
                'metadata': {},
                'capability': {
                    'hash': 'hash',
                    'version': 'ver'
                },
            } for name in ('one', 'two')
        ])
        # listing should return 3
        listing = self.successResultOf(self.group.list_webhooks('2'))
        self.assertGreater(len(listing), len(creation))

    def test_get_webhook_nonexistent_policy_fails(self):
        """
        Updating a webhook of a nonexistant policy fails with a
        :class:`NoSuchPolicyError`.
        """
        deferred = self.group.get_webhook("puppies", "1")
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_get_nonexistant_webhook_fails(self):
        """
        Getting a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        self.group.webhooks = {'2': {}}
        deferred = self.group.get_webhook("2", "1")
        self.failureResultOf(deferred, NoSuchWebhookError)

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
        self.assertEqual(self.successResultOf(deferred),
                         expected_webhook)

    def test_update_webhook_nonexistent_policy_fails(self):
        """
        Updating a webhook of a nonexistant policy fails with a
        :class:`NoSuchPolicyError`.
        """
        deferred = self.group.update_webhook("puppies", "1", {'name': 'fake'})
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_update_nonexistant_webhook_fails(self):
        """
        Updating a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        deferred = self.group.update_webhook("2", "1", {'name': 'fake'})
        self.failureResultOf(deferred, NoSuchWebhookError)

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
        self.assertIsNone(self.successResultOf(deferred))
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
        self.assertIsNone(self.successResultOf(deferred))
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
        self.failureResultOf(deferred, NoSuchPolicyError)

    def test_delete_nonexistant_webhook_fails(self):
        """
        Deleting a non-existant webhook of an existing policy fails with a
        :class:`NoSuchWebhookError`.
        """
        self.group.policies = {'2': {}}
        deferred = self.group.delete_webhook("2", "1")
        self.failureResultOf(deferred, NoSuchWebhookError)

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
        self.assertIsNone(self.successResultOf(deferred))
        self.assertEqual(self.group.webhooks, {'2': {}})


class MockScalingScheduleCollectionTestCase(IScalingScheduleCollectionProviderMixin,
                                            TestCase):
    """
    Tests for :class:`MockScalingGroupCollection`
    """

    def setUp(self):
        """ Set up the mocks """
        self.collection = MockScalingGroupCollection()
        self.tenant_id = 'goo1234'
        self.mock_log = mock.MagicMock()

    def test_fetch_events(self):
        """
        Test that the `fetch_and_delete` method works.
        """
        deferred = self.collection.fetch_and_delete(2, 1234, 100)
        self.assertEqual(self.successResultOf(deferred), [])


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
        self.launch = group_examples.launch_server_config()[1]
        self.mock_log = mock.MagicMock()

        self.counter = 0

        def generate_uuid():
            self.counter += 1
            return self.counter

        self.mock_uuid = patch(self, 'otter.models.mock.uuid4',
                               side_effect=generate_uuid)

    def test_list_scaling_groups_is_empty_if_new_tenant_id(self):
        """
        Listing all scaling groups for a tenant id, with no scaling groups
        because they are a new tenant id, returns an empty list
        """
        self.assertEqual(self.validate_list_states_return_value(
            self.mock_log, self.tenant_id), [],
            "Should start off with zero groups for tenant")

    @mock.patch('otter.models.mock.MockScalingGroup', wraps=MockScalingGroup)
    def test_create_group_with_config_and_list_scaling_group_states(self, mock_sgrp):
        """
        Listing scaling group states returns one :class:`GroupState` per group,
        and adding another scaling group increases the number of scaling groups
        in the collection.  These are tested together since testing list
        involves putting scaling groups in the collection (create), and testing
        creation involves enumerating the collection (list)

        Creation of a scaling group with a 'config' parameter creates a
        scaling group with the specified configuration.
        """
        policies = group_examples.policy()[:2]
        self.assertEqual(self.validate_list_states_return_value(
                         self.mock_log, self.
                         tenant_id), [],
                         "Should start off with zero groups")
        manifest = self.validate_create_return_value(
            self.mock_log, self.tenant_id, self.config, self.launch, policies)

        self.assertEqual(self.mock_uuid.call_count, 3)  # 1 group, 3 policies

        expected_policies = [
            dict(id='2', **policies[0]),
            dict(id='3', **policies[1])
        ]

        self.assertEqual(manifest, {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'state': GroupState(self.tenant_id, "1", "", {}, {}, "0001-01-01T00:00:00Z", {}, False),
            'scalingPolicies': expected_policies,
            'id': '1'
        })

        result = self.validate_list_states_return_value(self.mock_log, self.tenant_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].group_id, '1', "Group not added to collection")

        mock_sgrp.assert_called_once_with(
            mock.ANY, self.tenant_id, '1', self.collection,
            {'config': self.config, 'launch': self.launch, 'policies': policies})

    def test_list_scaling_group_limits_number_of_groups(self):
        """
        Listing all scaling groups limits the number of groups by the limit
        specified
        """
        log = mock_log()
        for i in range(9):
            self.collection.create_scaling_group(log, '1', '', '', [])

        result = self.successResultOf(
            self.collection.list_scaling_group_states(log, '1', limit=3))
        self.assertEqual([g.group_id for g in result], ['1', '2', '3'])

    def test_list_scaling_group_offsets_by_marker(self):
        """
        Listing all scaling groups will offset the list by the last seen
        parameter
        """
        log = mock_log()
        for i in range(9):
            self.collection.create_scaling_group(log, '1', '', '', [])

        result = self.successResultOf(
            self.collection.list_scaling_group_states(log, '1', marker='5'))
        self.assertEqual([g.group_id for g in result], ['6', '7', '8', '9'])

    @mock.patch('otter.models.mock.MockScalingGroup', wraps=MockScalingGroup)
    def test_create_group_with_no_policies(self, mock_sgrp):
        """
        Creating a scaling group with all arguments except policies passes None
        as policies to the MockScalingGroup.
        """
        manifest = self.successResultOf(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, {}))  # empty launch for testing

        self.assertEqual(self.mock_uuid.call_count, 1)

        uuid = manifest['id']
        self.assertEqual(uuid, '1')

        mock_sgrp.assert_called_once_with(
            mock.ANY, self.tenant_id, uuid, self.collection,
            {'config': self.config, 'launch': {}, 'policies': None})

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
        manifest = self.successResultOf(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, launch, {}))

        group = self.collection.get_scaling_group(self.mock_log, self.tenant_id,
                                                  manifest['id'])

        pol_rec = self.successResultOf(group.create_policies([policy]))

        pol_uuid = pol_rec[0]['id']

        self.successResultOf(group.create_webhooks(pol_uuid, [{}]))

        deferred = self.collection.webhook_info_by_hash(self.mock_log, 'hash')
        webhook_info = self.successResultOf(deferred)
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
        manifest = self.successResultOf(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, launch, {}))

        group = self.collection.get_scaling_group(self.mock_log, self.tenant_id,
                                                  manifest['id'])

        pol_rec = self.successResultOf(group.create_policies([policy]))

        pol_uuid = pol_rec[0]['id']

        self.successResultOf(group.create_webhooks(pol_uuid, [{}]))

        deferred = self.collection.webhook_info_by_hash(self.mock_log, 'weasel')
        self.failureResultOf(deferred, UnrecognizedCapabilityError)

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

        group.policies = {'1': {}, '2': {}, '3': {}}
        group.webhooks = {'1': {}, '2': {}, '3': {'3x': {}}}

        return [
            group.view_config(),
            group.view_launch_config(),
            group.view_state(),
            group.update_config({
                'name': 'aname',
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
            group.delete_webhook('3', '3x'),
            group.delete_group()
        ]

    def test_get_scaling_group_returns_mock_scaling_group(self):
        """
        Getting valid scaling group returns a MockScalingGroup whose methods
        work.
        """
        manifest = self.successResultOf(
            self.collection.create_scaling_group(
                self.mock_log, self.tenant_id, self.config, {}))  # empty launch for testing
        uuid = manifest['id']

        succeeded_deferreds = self._call_all_methods_on_group(uuid)
        for deferred in succeeded_deferreds:
            self.successResultOf(deferred)

    def test_get_scaling_group_works_but_methods_do_not(self):
        """
        Getting a scaling group that doesn't exist returns a MockScalingGropu
        whose methods will raise :class:`NoSuchScalingGroupError` exceptions.
        """
        failed_deferreds = self._call_all_methods_on_group("1")

        for deferred in failed_deferreds:
            self.failureResultOf(deferred, NoSuchScalingGroupError)


class MockAdminTestCase(TestCase):
    """
    Tests for :class:`MockAdmin`
    """

    def setUp(self):
        """ Setup mocks """
        self.collection = MockAdmin()
        self.mock_log = mock.MagicMock()

    def test_get_metrics_returns_mock_metrics(self):
        """
        Getting mock metrics will return an empty dict.
        """
        deferred = self.collection.get_metrics(self.mock_log)
        self.assertEqual(self.successResultOf(deferred), {})
