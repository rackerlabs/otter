"""
Tests for :mod:`otter.models.mock`
"""

from twisted.trial.unittest import TestCase

from otter.models.mock import MockScalingGroup, MockScalingGroupCollection
from otter.models.interface import NoSuchScalingGroup

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
            'region': 'DFW',
            'cooldown': 600,
            'min_servers': 0,
            'max_servers': 10,
            'steady_state_servers': 4,
            'metadata': {}
        })


    # def test_group(self):
    #     """ Test the scaling group """
    #     d = self.db.create_scaling_group('goo1243', mock_group)
    #     id = self.assert_deferred_fired(d)
    #     group = self.db.get_scaling_group('goo1243', id)
    #     d = group.view()
    #     r = self.assert_deferred_fired(d)
    #     self.assertEqual(r, mock_group)
    #     d = group.update_scaling_group(edit_group)
    #     r = self.assert_deferred_fired(d)
    #     d = group.view()
    #     r = self.assert_deferred_fired(d)
    #     self.assertEqual(r, edit_group)


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

    def test_create_and_list_scaling_groups(self):
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

        for key in self.config:
            self.assertEqual(self.config[key],
                             getattr(result[uuid], key, None))

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
        :class:`NoSuchScalingGroup` exception
        """
        self.assert_deferred_failed(
            self.collection.delete_scaling_group(self.tenant_id, 1),
            NoSuchScalingGroup)

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
        :class:`NoSuchScalingGroup` exception
        """
        self.assert_deferred_failed(
            self.collection.get_scaling_group(self.tenant_id, 1),
            NoSuchScalingGroup)
