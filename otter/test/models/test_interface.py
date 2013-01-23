"""
Tests for :mod:`otter.models.interface`
"""
from jsonschema import validate

from zope.interface.verify import verifyObject

from otter.models.interface import IScalingGroup, IScalingGroupCollection
from otter.json_schema.group_schemas import launch_config
from otter.json_schema import model_schemas
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
        validate(result, model_schemas.view_manifest)
        return result

    def validate_view_config_return_value(self, *args, **kwargs):
        """
        Calls ``view_config()``, and validates that it returns a config
        dictionary containing relevant configuration values, as specified by
        the :data:`config`

        :return: the return value of ``view_config()``
        """
        result = self.assert_deferred_succeeded(
            self.group.view_config(*args, **kwargs))
        validate(result, model_schemas.group_config)
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
        result = self.assert_deferred_succeeded(
            self.group.view_state(*args, **kwargs))
        validate(result, model_schemas.group_state)
        return result

    def validate_list_policies_return_value(self, *args, **kwargs):
        """
        Calls ``list_policies``, and validates that it returns a policy
        dictionary containing the policies mapped to their IDs

        :return: the return value of ``list_policies()``
        """
        result = self.assert_deferred_succeeded(
            self.group.list_policies(*args, **kwargs))
        validate(result, model_schemas.policy_list)
        return result

    def validate_create_policies_return_value(self, *args, **kwargs):
        """
        Calls ``list_policies``, and validates that it returns a policy
        dictionary containing the policies mapped to their IDs

        :return: the return value of ``list_policies()``
        """
        result = self.assert_deferred_succeeded(
            self.group.create_policies(*args, **kwargs))
        validate(result, model_schemas.policy_list)
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
