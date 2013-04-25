"""
Tests for :mod:`otter.models.interface`
"""
from jsonschema import validate

from zope.interface.verify import verifyObject

from twisted.trial.unittest import TestCase

from otter.models.interface import (
    GroupState, IScalingGroup, IScalingGroupCollection, IScalingGroupState)
from otter.json_schema.group_schemas import launch_config
from otter.json_schema import model_schemas
from otter.test.utils import DeferredTestMixin


class GroupStateTestCase(TestCase):
    """
    Tests the state object `otter.mode.s
    """
    def test_add_job_success(self):
        """
        If the job ID is not in the pending list, ``add_job`` adds it along with
        the creation time.
        """
        state = GroupState('tid', 'gid', {}, {}, True, {}, None,
                           now=lambda: 'datetime')
        state.add_job('1')
        self.assertEqual(state.pending, {'1': {'created': 'datetime'}})

    def test_add_job_fails(self):
        """
        If the job ID is in the pending list, ``add_job`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {}, {'1': {}}, True, {}, None)
        self.assertRaises(AssertionError, state.add_job, '1')
        self.assertEqual(state.pending, {'1': {}})

    def test_del_job_success(self):
        """
        If the job ID is in the pending list, ``del_job`` removes it.
        """
        state = GroupState('tid', 'gid', {}, {'1': {}}, True, {}, None)
        state.del_job('1')
        self.assertEqual(state.pending, {})

    def test_del_job_fails(self):
        """
        If the job ID is not in the pending list, ``del_job`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {}, {}, True, {}, None)
        self.assertRaises(AssertionError, state.del_job, '1')
        self.assertEqual(state.pending, {})

    def test_add_active_success_adds_creation_time(self):
        """
        If the server ID is not in the active list, ``add_active`` adds it along
        with server info, and adds the creation time to server info that
        does not already have it.
        """
        state = GroupState('tid', 'gid', {}, {}, True, {}, None,
                           now=lambda: 'datetime')
        state.add_active('1', {'stuff': 'here'})
        self.assertEqual(state.active,
                         {'1': {'stuff': 'here', 'created': 'datetime'}})

    def test_add_active_success_preserves_creation_time(self):
        """
        If the server ID is not in the active list, ``add_active`` adds it along
        with server info, and does not change the server info's creation time.
        """
        state = GroupState('tid', 'gid', {}, {}, True, {}, None,
                           now=lambda: 'other_now')
        state.add_active('1', {'stuff': 'here', 'created': 'now'})
        self.assertEqual(state.active,
                         {'1': {'stuff': 'here', 'created': 'now'}})

    def test_add_active_fails(self):
        """
        If the server ID is in the active list, ``add_active`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {'1': {}}, {}, True, {}, None)
        self.assertRaises(AssertionError, state.add_active, '1', {'1': '2'})
        self.assertEqual(state.active, {'1': {}})

    def test_mark_executed_updates_policy_and_group(self):
        """
        Marking executed updates the policy touched and group touched to the
        same time.
        """
        t = ['0']
        state = GroupState('tid', 'gid', {}, {}, True, {}, None, now=t.pop)
        state.mark_executed('pid')
        self.assertEqual(state.group_touched, '0')
        self.assertEqual(state.policy_touched, {'pid': '0'})


class IScalingGroupStateProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides
    :class:`otter.models.interface.IScalingGroupState`.

    :ivar group: an instance of an
        :class:`otter.models.interface.IScalingGroupState` provider
    """

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.models.interface.IScalingGroupState`.
        """
        verifyObject(IScalingGroupState, self.state)


class IScalingGroupProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides
    :class:`otter.models.interface.IScalingGroup`.

    :ivar group: an instance of an
        :class:`otter.models.interface.IScalingGroup` provider
    """

    sample_webhook_data = {
        'name': 'a name',
        'metadata': {},
        'capability': {'hash': 'h', 'version': '1'}
    }

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.models.interface.IScalingGroup`.
        """
        verifyObject(IScalingGroup, self.group)

    def validate_view_manifest_return_value(self, *args, **kwargs):
        """
        Calls ``view_manifest()``, and validates that it returns a
        dictionary containing relevant configuration values, as specified
        by :data:`model_schemas.manifest`

        :return: the return value of ``view_manifest()``
        """
        result = self.assert_deferred_succeeded(
            self.group.view_manifest(*args, **kwargs))
        validate(result, model_schemas.manifest)
        return result

    def validate_view_config_return_value(self, *args, **kwargs):
        """
        Calls ``view_config()``, and validates that it returns a config
        dictionary containing relevant configuration values, as specified by
        the :data:`model_schemas.group_config`

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

    def validate_list_webhooks_return_value(self, *args, **kwargs):
        """
        Calls ``list_webhooks(policy_id)`` and validates that it returns a
        dictionary uuids mapped to webhook JSON blobs.

        :return: the return value of ``list_webhooks(policy_id)``
        """
        result = self.assert_deferred_succeeded(
            self.group.list_webhooks(*args, **kwargs))
        validate(result, model_schemas.webhook_list)
        return result

    def validate_create_webhooks_return_value(self, *args, **kwargs):
        """
        Calls ``create_webhooks(policy_id, data)`` and validates that it returns
        a dictionary uuids mapped to webhook JSON blobs.

        :return: the return value of ``create_webhooks(policy_id, data)``
        """
        result = self.assert_deferred_succeeded(
            self.group.create_webhooks(*args, **kwargs))
        validate(result, model_schemas.webhook_list)
        return result

    def validate_get_webhook_return_value(self, *args, **kwargs):
        """
        Calls ``get_webhook(policy_id, webhook_id)`` and validates that it
        returns a dictionary uuids mapped to webhook JSON blobs.

        :return: the return value of ``get_webhook(policy_id, webhook_id)``
        """
        result = self.assert_deferred_succeeded(
            self.group.get_webhook(*args, **kwargs))
        validate(result, model_schemas.webhook)
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

    def validate_create_return_value(self, *args, **kwargs):
        """
        Calls ``create_scaling_Group()``, and validates that it returns a
        dictionary containing relevant configuration values, as specified
        by :data:`model_schemas.manifest`

        :return: the return value of ``create_scaling_group()``
        """
        result = self.successResultOf(
            self.collection.create_scaling_group(*args, **kwargs))
        validate(result, model_schemas.manifest)
        return result

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
