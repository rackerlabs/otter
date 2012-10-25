"""
Test the scaling groups interface
"""
from twisted.trial.unittest import TestCase

from otter import scaling_groups_mock
from otter.test.utils import DeferredTestMixin

mock_group = {
    'name': 'blah',
    'regions': [],
    'cooldown': 600,
    'min_servers': 0,
    'max_servers': 10,
    'desired_servers': 4,
    'metadata': {}
}

edit_group = {
    'name': 'blah2',
    'regions': [],
    'cooldown': 200,
    'min_servers': 1,
    'max_servers': 20,
    'desired_servers': 3,
    'metadata': {}
}


class ScalingGroupsEndpointTestCase(DeferredTestMixin, TestCase):
    """
    Represents unit tests for the entity objects and data store
    """

    def setUp(self):
        """ Setup the mocks """
        self.db = scaling_groups_mock.MockScalingGroupCollection()
        self.db.mock_add_tenant('goo1243')

    def test_crud(self):
        """ Test CRUD operations on the overall structure """
        d = self.db.create_scaling_group('goo1243', mock_group)
        id = self.assert_deferred_fired(d)
        d = self.db.list_scaling_groups('goo1243')
        r = self.assert_deferred_fired(d)
        self.assertIn(id, r)
        group = self.db.get_scaling_group('goo1243', id)
        d = group.view()
        r = self.assert_deferred_fired(d)
        self.assertEqual(r, mock_group)
        d = self.db.delete_scaling_group('goo1243', id)
        r = self.assert_deferred_fired(d)
        d = self.db.list_scaling_groups('goo1243')
        r = self.assert_deferred_fired(d)
        self.assertNotIn(id, r)
        self.assertEqual(len(r), 0)

    def test_group(self):
        """ Test the scaling group """
        d = self.db.create_scaling_group('goo1243', mock_group)
        id = self.assert_deferred_fired(d)
        group = self.db.get_scaling_group('goo1243', id)
        d = group.view()
        r = self.assert_deferred_fired(d)
        self.assertEqual(r, mock_group)
        d = group.update_scaling_group(edit_group)
        r = self.assert_deferred_fired(d)
        d = group.view()
        r = self.assert_deferred_fired(d)
        self.assertEqual(r, edit_group)
