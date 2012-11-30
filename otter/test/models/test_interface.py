"""
Tests for :mod:`otter.models.interface`
"""
from copy import deepcopy

from jsonschema import Draft3Validator, validate, ValidationError

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    scaling_group_config_schema)
from otter.test.utils import DeferredTestMixin


scaling_group_state_schema = {
    'type': 'object',
    'properties': {
        'steady_state_entities': {
            'type': 'integer',
            'minimum': 0,
            'required': True
        },
        'current_entities': {
            'type': 'integer',
            'minimum': 0,
            'required': True
        }
    },
    'additionalProperties': False
}


class IScalingGroupProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides :class:`IScalingGroup`.

    :ivar group: an instance of an :class:`IScalingGroup` provider
    """

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.scaling_groups_interface.IScalingGroup`.
        """
        verifyObject(IScalingGroup, self.group)

    def validate_list_return_value(self, *args, **kwargs):
        """
        Calls ``list()``, and validates it returns a list of strings

        :return: the return value of ``list()``
        """
        result = self.assert_deferred_succeeded(
            defer.maybeDeferred(self.group.list_entities, *args, **kwargs))
        validate(result, {
            "type": "array",
            "items": {
                "type": "string"
            }
        })
        return result

    def validate_view_config_return_value(self, *args, **kwargs):
        """
        Calls ``view_config()``, and validates that it returns a config
        dictionary containing relevant configuration values, as specified by
        the :data:`scaling_group_config_schema`

        :return: the return value of ``view_config()``
        """
        # unlike updating or inputing a group config, the returned config
        # must actually have all the properties
        schema = deepcopy(scaling_group_config_schema)
        for property_name in schema['properties']:
            schema['properties'][property_name]['required'] = True

        result = self.assert_deferred_succeeded(
            defer.maybeDeferred(self.group.view_config, *args, **kwargs))
        validate(result, schema)
        return result

    def validate_view_state_return_value(self, *args, **kwargs):
        """
        Calls ``view_state()``, and validates that it returns a state
        dictionary containing relevant state values

        :return: the return value of ``view_state()``
        """
        # unlike updating or inputing a group config, the returned config
        # must actually have all the properties
        result = self.assert_deferred_succeeded(
            defer.maybeDeferred(self.group.view_state, *args, **kwargs))
        validate(result, scaling_group_state_schema)
        return result


class IScalingGroupCollectionProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides
    :class:`IScalingGroupCollection`.

    :ivar collection: an instance of the :class:`IScalingGroup` provider
    """

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.scaling_groups_interface.IScalingGroup`.
        """
        verifyObject(IScalingGroupCollection, self.collection)

    def validate_list_return_value(self, *args, **kwargs):
        """
        Calls ``list_scaling_groups()`` and validates that it returns a
        dictionary of a dictionary of lists of :class:`IScalingGroup` providers

        :return: the return value of ``list_scaling_groups()``
        """
        result = self.assert_deferred_succeeded(defer.maybeDeferred(
            self.collection.list_scaling_groups,
            *args, **kwargs))

        # not valid JSON, since the ultimate objects are IScalingGroup
        # objects, so assert that it's a dictionary, all its
        # keys are strings, all its values are dicts whose keys are strings
        # and whose values are IScalingGroups
        self.assertEqual(type(result), dict)
        for key in result:
            self.assertEqual(type(key), str)
        for group_list in result.values():
            self.assertEqual(type(group_list), list)
            for group in group_list:
                self.assertTrue(IScalingGroup.providedBy(group))

        return result

    def validate_get_return_value(self, *args, **kwargs):
        """
        Calls ``get_scaling_group()`` and validates that it returns a
        :class:`IScalingGroup` provider

        :return: the return value of ``get_scaling_group()``
        """
        result = self.assert_deferred_succeeded(defer.maybeDeferred(
            self.collection.get_scaling_group, *args, **kwargs))
        self.assertTrue(IScalingGroup.providedBy(result))
        return result


class ScalingGroupConfigTestCase(TestCase):
    """
    Simple verification that the JSON schema for scaling groups is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is valid Draft 3 schema
        """
        Draft3Validator.check_schema(scaling_group_config_schema)

    def test_all_properties_have_titles(self):
        """
        All the properties in the schema should have titles
        """
        for property_name in scaling_group_config_schema['properties']:
            prop = scaling_group_config_schema['properties'][property_name]
            self.assertTrue('title' in prop)

    def test_minimal_config_validates(self):
        """
        Providing nothing will validate.  This is necessary because this may
        be the minimum schema the user provides.
        """
        validate({'name': 'blah', 'cooldown': 60, 'min_entities': 0},
                 scaling_group_config_schema)

    def test_extra_values_does_not_validate(self):
        """
        Providing non-expected properties will fail validate.
        """
        self.assertRaises(ValidationError, validate, {'what': 'not expected'},
                          scaling_group_config_schema)

    def test_anything_in_metadata_validates(self):
        """
        Putting all sorts of data into the metadata will still validate
        """
        config = {
            'name': 'blah',
            'cooldown': 60,
            'min_entities': 0,
            'metadata': {
                'somekey': 'somevalue',
                'alist': [],
                'adict': {
                    'dictkey': 5
                }
            }
        }
        validate(config, scaling_group_config_schema)
