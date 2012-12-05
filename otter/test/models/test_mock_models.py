"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.models.mock import MockScalingGroup, MockScalingGroupCollection
from otter.models.interface import NoSuchScalingGroupError, NoSuchEntityError

from otter.test.models.test_interface import (
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin)


class MockScalingGroupTestCase(IScalingGroupProviderMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.group = MockScalingGroup('DFW', 1, config={})

    def test_default_view_config_has_all_info(self):
        """
        View should return a dictionary that conforms to the JSON schema (has
        all parameters even though only a few were passed in)
        """
        result = self.validate_view_config_return_value()
        self.assertEqual(result, {
            'name': '',
            'cooldown': 0,
            'minEntities': 0,
            'maxEntities': None,
            'metadata': {}
        })

    def test_list_returns_valid_scheme(self):
        """
        ``list_entities`` returns something conforming to the scheme whether or
        not there are entities in the system
        """
        self.assertEqual(self.validate_list_return_value(), [])
        self.group.entities = ["1", "2", "3"]
        self.assertEqual(self.validate_list_return_value(), ["1", "2", "3"])

    def test_view_state_returns_valid_scheme(self):
        """
        ``view_state`` returns something conforming to the scheme whether or
        not there are entities in the system
        """
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 0,
            'current_entities': 0
        })
        self.group.entities = ["1", "2", "3"]
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 0,
            'current_entities': 3
        })

    def test_set_steady_state_does_not_exceed_min(self):
        """
        Setting a steady state that is below the min will set the steady state
        to the min.
        """
        self.group = MockScalingGroup('DFW', 1, {'minEntities': 5})
        self.assert_deferred_succeeded(self.group.set_steady_state(1))
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 5,
            'current_entities': 0
        })

    def test_set_steady_state_does_not_exceed_max(self):
        """
        Setting a steady state that is above the max will set the steady state
        to the max.
        """
        self.group = MockScalingGroup('DFW', 1, {'maxEntities': 5})
        self.assert_deferred_succeeded(self.group.set_steady_state(10))
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 5,
            'current_entities': 0
        })

    def test_set_steady_state_within_limit_succeeds(self):
        """
        Setting a steady state that is between the min and max will set the
        steady state to to the specified number.
        """
        self.assert_deferred_succeeded(self.group.set_steady_state(10))
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 10,
            'current_entities': 0
        })

    def test_bounce_existing_entity_succeeds(self):
        """
        Bouncing an existing entity succeeds (and does not change the list
        view)
        """
        self.group.entities = ["1"]
        self.assertIsNone(self.assert_deferred_succeeded(
            self.group.bounce_entity("1")))
        self.assertEqual(self.validate_list_return_value(), ["1"])
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 0,
            'current_entities': 1
        })

    def test_bounce_invalid_entity_fails(self):
        """
        Bouncing an invalid valid entity fails
        """
        self.assert_deferred_failed(
            self.group.bounce_entity("1"), NoSuchEntityError)
        self.assertEqual(self.validate_list_return_value(), [])
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 0,
            'current_entities': 0
        })

    def test_update_config_updates_ignores_invalid_keys(self):
        """
        Passing in a dict only updates the desired fields that are provided
        """
        expected = {
            'cooldown': 1000,
            'metadata': {'UPDATED': 'UPDATED'},
            'minEntities': 100,
            'maxEntities': 1000,
            'name': 'UPDATED'
        }
        extra = dict(expected)
        extra['non-param'] = 'UPDATED'

        self.assert_deferred_succeeded(self.group.update_config(extra))
        result = self.validate_view_config_return_value()
        self.assertEqual(result, expected)

    def test_update_config_does_not_overwrite_existing_non_provided_keys(self):
        """
        If certain keys are not provided in the update dictionary, the keys
        that are not provided are not overwritten.
        """
        expected = {
            'cooldown': 1000,
            'metadata': {'UPDATED': 'UPDATED'},
            'minEntities': 100,
            'maxEntities': 1000,
            'name': 'UPDATED'
        }
        self.assert_deferred_succeeded(self.group.update_config(expected))
        self.assert_deferred_succeeded(self.group.update_config({}))
        result = self.validate_view_config_return_value()
        self.assertEqual(result, expected)

    def test_update_config_min_updates_steady_state(self):
        """
        If the updated min is greater than the current steady state, the
        current steady state is set to that min
        """
        self.assert_deferred_succeeded(self.group.update_config({
            'minEntities': 5
        }))
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 5,
            'current_entities': 0
        })

    def test_update_config_max_updates_steady_state(self):
        """
        If the updated max is less than the current steady state, the
        current steady state is set to that max
        """
        self.assert_deferred_succeeded(self.group.set_steady_state(10))
        self.assert_deferred_succeeded(self.group.update_config({
            'maxEntities': 5
        }))
        self.assertEquals(self.validate_view_state_return_value(), {
            'steady_state_entities': 5,
            'current_entities': 0
        })


class MockScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`MockScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.collection = MockScalingGroupCollection()
        self.tenant_id = 'goo1234'
        self.collection.mock_add_tenant(self.tenant_id)
        self.region = 'DFW'
        self.config = {
            'name': 'blah',
            'cooldown': 600,
            'minEntities': 0,
            'maxEntities': 10,
            'metadata': {}
        }

    def test_list_scaling_groups_is_empty_if_no_groups(self):
        """
        Listing all scaling groups for a tenant id, with no scaling groups,
        returns an empty dictionary
        """
        self.assertEqual(self.validate_list_return_value(self.tenant_id), {},
                         "Should start off with zero groups for tenant")

    def test_list_scaling_groups_has_empty_region_if_called_with_region(self):
        """
        Listing all scaling groups for a region for a tenant id will return
        a dictionary with that region as a key and an empty dictionary as a
        value
        """
        self.assertEqual(
            self.validate_list_return_value(self.tenant_id, self.region),
            {self.region: []},
            "Should start off with zero groups for region for tenant")

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
        self.assertEqual(self.validate_list_return_value(self.tenant_id), {},
                         "Should start off with zero groups")
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.tenant_id, self.region, self.config))

        result = self.validate_list_return_value(self.tenant_id, self.region)
        self.assertEqual(len(result[self.region]), 1)
        self.assertEqual(result[self.region][0].uuid, uuid,
                         "Group not added to collection")

        mock_sgrp.assert_called_once_with(self.region, uuid, self.config)

    def test_delete_removes_a_scaling_group(self):
        """
        Deleting a valid scaling group decreases the number of scaling groups
        in the collection
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.tenant_id, self.region, self.config))

        result = self.validate_list_return_value(self.tenant_id, self.region)
        self.assertEqual(len(result[self.region]), 1,
                         "Group not added correctly")

        self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.tenant_id,
                                                 self.region, uuid))

        result = self.validate_list_return_value(self.tenant_id)
        self.assertEqual(result, {}, "Group not deleted from collection")

    def test_delete_scaling_group_fails_if_scaling_group_does_not_exist(self):
        """
        Deleting a scaling group that doesn't exist raises a
        :class:`NoSuchScalingGroupError` exception
        """
        deferred = self.collection.delete_scaling_group(self.tenant_id,
                                                        self.region, 1)
        self.assert_deferred_failed(deferred, NoSuchScalingGroupError)

    def test_get_scaling_group_returns_mock_scaling_group(self):
        """
        Getting valid scaling group returns a MockScalingGroup whose methods
        work.
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(
                self.tenant_id, self.region, self.config))
        group = self.validate_get_return_value(self.tenant_id, self.region,
                                               uuid)
        self.assertTrue(isinstance(group, MockScalingGroup),
                        "group is {0!r}".format(group))

        for method in ('view_config', 'view_state', 'list_entities'):
            self.assert_deferred_succeeded(getattr(group, method)())

        self.assert_deferred_succeeded(group.update_config({}))
        self.assert_deferred_succeeded(group.set_steady_state(1))

        group.entities = [1]
        self.assert_deferred_succeeded(group.bounce_entity(1))

    def test_get_scaling_group_works_but_methods_do_not(self):
        """
        Getting a scaling group that doesn't exist returns a MockScalingGropu
        whose methods will raise :class:`NoSuchScalingGroupError` exceptions.
        """
        group = self.validate_get_return_value(self.tenant_id, self.region, 1)
        self.assertTrue(isinstance(group, MockScalingGroup),
                        "group is {0!r}".format(group))

        for method in ('view_config', 'view_state', 'list_entities'):
            self.assert_deferred_failed(getattr(group, method)(),
                                        NoSuchScalingGroupError)

        self.assert_deferred_failed(group.update_config({}),
                                    NoSuchScalingGroupError)
        self.assert_deferred_failed(group.set_steady_state(1),
                                    NoSuchScalingGroupError)
        group.entities = [1]
        self.assert_deferred_failed(group.bounce_entity(1),
                                    NoSuchScalingGroupError)
