"""
Tests for :mod:`otter.models.interface`
"""
from copy import deepcopy

from jsonschema import validate

from zope.interface.verify import verifyObject

from otter.models.interface import IScalingGroup, IScalingGroupCollection
from otter.json_schema.scaling_group import config, create_group, launch_config
from otter.test.utils import DeferredTestMixin


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

    def validate_view_manifest_return_value(self, *args, **kwargs):
        """
        Calls ``view_manifest()``, and validates that it returns a
        dictionary containing relevant configuration values, as specified
        by :data:`create_group`

        :return: the return value of ``view_manifest()``
        """
        result = self.assert_deferred_succeeded(
            self.group.view_manifest(*args, **kwargs))
        validate(result, create_group)
        return result

    def validate_view_config_return_value(self, *args, **kwargs):
        """
        Calls ``view_config()``, and validates that it returns a config
        dictionary containing relevant configuration values, as specified by
        the :data:`config`

        :return: the return value of ``view_config()``
        """
        # unlike updating or inputing a group config, the returned config
        # must actually have all the properties
        schema = deepcopy(config)
        for property_name in schema['properties']:
            schema['properties'][property_name]['required'] = True

        result = self.assert_deferred_succeeded(
            self.group.view_config(*args, **kwargs))
        validate(result, schema)
        return result

    def validate_view_launch_config_return_value(self, *args, **kwargs):
        """
        Calls ``view_launch_config()``, and validates that it returns a launch
        config dictionary containing relevant configuration values, as
        specified by the :data:`launch_config`

        :return: the return value of ``view_launch_config()``
        """
        result = self.assert_deferred_succeeded(
            self.group.view_config(*args, **kwargs))
        validate(result, launch_config)
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
            self.group.view_state(*args, **kwargs))
        entity_schema = {
            'type': 'object',
            'patternProperties': {
                "^\S+$": {
                    'type': 'array',
                    'required': True,
                    'uniqueItems': True,
                    'minItems': 1,
                    'items': {
                        "type": "object",
                        "properties": {
                            'rel': {
                                'type': 'string',
                                'required': True
                            },
                            'href': {
                                'type': 'string',
                                'required': True
                            }
                        },
                        "additionalProperties": False
                    }
                }
            },
            'additionalProperties': False
        }
        validate(result, {
            'type': 'object',
            'properties': {
                'steadyState': {
                    'type': 'integer',
                    'minimum': 0,
                    'required': True
                },
                'paused': {
                    'type': 'boolean',
                    'required': True
                },
                'active': entity_schema,
                'pending': entity_schema
            },
            'additionalProperties': False
        })
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
        of :class:`IScalingGroup` providers

        :return: the return value of ``list_scaling_groups()``
        """
        result = self.assert_deferred_succeeded(
            self.collection.list_scaling_groups(*args, **kwargs))

        # not valid JSON, since the ultimate objects are IScalingGroup
        # objects, so assert that it's a dictionary, all its
        # keys are strings, all its values are dicts whose keys are strings
        # and whose values are IScalingGroups
        self.assertEqual(type(result), list)
        for group in result:
            self.assertTrue(IScalingGroup.providedBy(group))

        return result

    def validate_get_return_value(self, *args, **kwargs):
        """
        Calls ``get_scaling_group()`` and validates that it returns a
        :class:`IScalingGroup` provider

        :return: the return value of ``get_scaling_group()``
        """
        result = self.collection.get_scaling_group(*args, **kwargs)
        self.assertTrue(IScalingGroup.providedBy(result))
        return result
