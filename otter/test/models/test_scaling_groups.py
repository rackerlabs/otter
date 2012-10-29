"""
Tests for :module:`otter.models.interface` and :module:`otter.models.mock`
"""
from jsonschema import validate

from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from otter.models.interface import IScalingGroup, scaling_group_config_schema
from otter.models import mock as mock_model
from otter.test.utils import DeferredTestMixin


class IScalingGroupProviderMixin(DeferredTestMixin,):
    """
    Mixin that tests for anything that provides :class:`IScalingGroup`.

    :ivar group_factory: a factory that produces an IScalingGroup provider
    :type group_factory: callable
    """

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.scaling_groups_interface.IScalingGroup`.
        """
        verifyObject(IScalingGroup)

    def test_list_returns_something_iterable(self):
        """
        ``list()`` returns a list, or at least something iterable
        """
        validate(self.group_factory().list(), {
            "type": "list",
            "items": {
                "type": "string"
            }
        })

    def test_view_returns_config(self):
        """
        ``view()`` returns a config dictionary containing relevant
        configuration values, as specified by the
        :data:`scaling_group_config_schema`
        """
        # unlike updating or inputing a group config, the returned config
        # must actually have all the properties
        schema = scaling_group_config_schema
        for property_name in schema['properties']:
            schema['properties'][property_name]['required'] = True
        validate(self.group_factory().view(), schema)


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
        self.db = mock_model.MockScalingGroupCollection()
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
