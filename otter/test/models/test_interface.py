"""
Tests for :module:`otter.models.interface`
"""
from jsonschema import Draft3Validator, validate

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    scaling_group_config_schema)
from otter.test.utils import DeferredTestMixin


class IScalingGroupProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides :class:`IScalingGroup`.

    :ivar group: an instance of an :class`IScalingGroup` provider
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
            defer.maybeDeferred(self.group.list, *args, **kwargs))
        validate(result, {
            "type": "array",
            "items": {
                "type": "string"
            }
        })
        return result

    def validate_view_return_value(self, *args, **kwargs):
        """
        Calls ``view()``, and validates that it returns a config dictionary
        containing relevant configuration values, as specified by the
        :data:`scaling_group_config_schema`

        :return: the return value of ``view()``
        """
        # unlike updating or inputing a group config, the returned config
        # must actually have all the properties
        schema = scaling_group_config_schema
        for property_name in schema['properties']:
            schema['properties'][property_name]['required'] = True

        result = self.assert_deferred_succeeded(
            defer.maybeDeferred(self.group.view, *args, **kwargs))
        validate(result, schema)
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
        Calls ``list_scaling_groups()`` and validates that it returns a list
        of strings

        :return: the return value of ``list_scaling_groups()``
        """
        result = self.assert_deferred_succeeded(defer.maybeDeferred(
            self.collection.list_scaling_groups,
            *args, **kwargs))

        # can't JSON validate, so assert that it's a dictionary, all its
        # strings are keys, and that all its values are IScalingGroups
        self.assertEqual(type(result), dict)
        for key in result.keys():
            self.assertEqual(type(key), str)
        for value in result.values():
            self.assertTrue(IScalingGroup.providedBy(value))

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
        Providing only the name, entity_type, and region will validate.  This
        is necessary because this may be the minimum schema the user provides.
        """
        validate(
            {'name': 'blah', 'region': 'DFW', 'entity_type': 'servers'},
            scaling_group_config_schema)
