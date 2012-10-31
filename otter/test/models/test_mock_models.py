"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.models.mock import MockScalingGroup, MockScalingGroupCollection
from otter.models.interface import (NoSuchScalingGroupError,
                                    InvalidEntityError, NoSuchEntityError)

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
        self.group = MockScalingGroup(1, {
            'name': 'blah',
            'entity_type': 'servers',
            'region': 'DFW'
        })

    def test_view_has_all_info(self):
        """
        View should return a dictionary that conforms to the JSON schema (has
        all parameters even though only a few were passed in)
        """
        result = self.validate_view_return_value()
        self.assertEqual(result, {
            'name': 'blah',
            'entity_type': 'servers',
            'region': 'DFW',
            # the rest are the default values
            'cooldown': 0,
            'min_entities': 0,
            'max_entities': int(1e9),
            'steady_state_entities': 0,
            'metadata': {}
        })

    def test_list_with_no_entities_returns_valid_scheme(self):
        """
        If there are no entities in the scaling group, list returns something
        conforming to the scheme
        """
        self.assertEqual(self.validate_list_return_value(), [])

    def test_add_entity_succeeds_and_list_displays_it(self):
        """
        Adding a valid entity id adds the entity to the scaling group and it
        appears when listing.
        """
        self.assertIsNone(self.assert_deferred_succeeded(self.group.add("1")))
        self.assertEqual(self.validate_list_return_value(), ["1"])

    @mock.patch('otter.models.mock.is_entity_id_valid', return_value=False)
    def test_add_invalid_entity_fails(self, mock_validity):
        """
        Adding an invalid valid entity fails and it doesn't appears when
        listing.
        """
        self.assert_deferred_failed(self.group.add("1"), InvalidEntityError)
        self.assertEqual(self.validate_list_return_value(), [])

    def test_deleting_existing_entity_succeeds(self):
        """
        Deleting a valid entity id removes the entity from the scaling group
        """
        self.assert_deferred_succeeded(self.group.add("1"))
        self.assertEqual(self.validate_list_return_value(), ["1"])
        self.assertIsNone(self.assert_deferred_succeeded(
            self.group.delete("1")))
        self.assertEqual(self.validate_list_return_value(), [])

    def test_delete_invalid_entity_fails(self):
        """
        Deleting an invalid valid entity fails
        """
        self.assert_deferred_failed(self.group.delete("1"), NoSuchEntityError)
        self.assertEqual(self.validate_list_return_value(), [])

    def test_update_scaling_group_updates_values(self):
        """
        Passing in a dict only updates the desired fields that are provided
        """
        self.assert_deferred_succeeded(self.group.update({
            'name': 'UPDATED',
            'cooldown': 1000,
            'non-param': 'UPDATED'
        }))
        result = self.validate_view_return_value()
        self.assertEqual(result, {
            'name': 'UPDATED',
            'cooldown': 1000,
            # the rest of these values have not been updated
            'entity_type': 'servers',
            'region': 'DFW',
            'min_entities': 0,
            'max_entities': int(1e9),
            'steady_state_entities': 0,
            'metadata': {}
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

        self.config = {
            'name': 'blah',
            'entity_type': 'servers',
            'region': 'DFW',
            'cooldown': 600,
            'min_entities': 0,
            'max_entities': 10,
            'steady_state_entities': 4,
            'metadata': {}
        }

    @mock.patch('otter.models.mock.MockScalingGroup', wraps=MockScalingGroup)
    def test_create_and_list_scaling_groups(self, mock_msg):
        """
        Listing a scaling group returns a mapping of scaling group uuid to
        scaling group model, and adding another scaling group increases the
        number of scaling groups in the collection.  These are tested together
        since testing list involves putting scaling groups in the collection
        (create), and testing creation involves enumerating the collection
        (list)
        """
        self.assertEqual(self.validate_list_return_value(self.tenant_id), {},
                         "Should start off with zero groups")

        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(self.tenant_id, self.config))

        result = self.validate_list_return_value(self.tenant_id)
        self.assertEqual(result.keys(), [uuid],
                         "Group not added to collection")

        mock_msg.assert_called_once_with(uuid, self.config)

    def test_delete_removes_a_scaling_group(self):
        """
        Deleting a valid scaling group decreases the number of scaling groups
        in the collection
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(self.tenant_id, self.config))

        result = self.validate_list_return_value(self.tenant_id)
        self.assertEqual(len(result), 1, "Group not added correctly")

        self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.tenant_id, uuid))

        result = self.validate_list_return_value(self.tenant_id)
        self.assertEqual(result, {}, "Group not deleted from collection")

    def test_delete_scaling_group_fails_if_scaling_group_does_not_exist(self):
        """
        Deleting a scaling group that doesn't exist raises a
        :class:`NoSuchScalingGroupError` exception
        """
        self.assert_deferred_failed(
            self.collection.delete_scaling_group(self.tenant_id, 1),
            NoSuchScalingGroupError)

    def test_get_scaling_group_returns_mock_scaling_group(self):
        """
        Getting valid scaling group returns a MockScalingGroup
        """
        uuid = self.assert_deferred_succeeded(
            self.collection.create_scaling_group(self.tenant_id, self.config))
        group = self.validate_get_return_value(self.tenant_id, uuid)
        self.assertTrue(isinstance(group, MockScalingGroup),
                        "group is {0!r}".format(group))

    def test_get_scaling_group_fails_if_scaling_group_does_not_exist(self):
        """
        Getting a scaling group that doesn't exist raises a
        :class:`NoSuchScalingGroupError` exception
        """
        self.assert_deferred_failed(
            self.collection.get_scaling_group(self.tenant_id, 1),
            NoSuchScalingGroupError)
