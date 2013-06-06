"""
Tests for :mod:`otter.models.interface`
"""
from collections import namedtuple


import mock

from zope.interface.verify import verifyObject

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter.models.interface import (
    GroupState, IScalingGroup, IScalingGroupCollection, IScalingScheduleCollection,
    NoSuchScalingGroupError)
from otter.json_schema.group_schemas import launch_config
from otter.json_schema import model_schemas, validate
from otter.test.utils import DeferredTestMixin


class GroupStateTestCase(TestCase):
    """
    Tests the state object `otter.mode.s
    """
    def test_repr_str(self):
        """
        repr(GroupState) returns something human readable
        """
        state = GroupState('tid', 'gid', {'1': {}}, {}, 'date', {}, True)
        self.assertEqual(
            repr(state),
            "GroupState(tid, gid, {'1': {}}, {}, date, {}, True)")

    def test_two_states_are_equal_if_all_vars_are_equal(self):
        """
        Two groups with the same parameters (even if now is different) are
        equal
        """
        self.assertEqual(
            GroupState('tid', 'gid', {'1': {}}, {'2': {}}, 'date', {}, True),
            GroupState('tid', 'gid', {'1': {}}, {'2': {}}, 'date', {}, True,
                       now=lambda: 'meh'))

    def test_two_states_are_unequal_if_vars_different(self):
        """
        Two groups with any different parameters are unequal
        """
        args = ('tid', 'gid', {}, {}, 'date', {}, True)

        def perterb(args, index):
            copy = [arg for arg in args]
            if isinstance(copy[index], str):
                copy[index] += '_'
            elif isinstance(copy[index], bool):
                copy[index] = not copy[index]
            else:  # it's a dict
                copy[index] = {'1': {}}
            return copy

        for i in range(len(args)):
            self.assertNotEqual(GroupState(*args), GroupState(*(perterb(args, i))))

    def test_a_state_is_not_equal_to_something_else(self):
        """
        The classes of the two objects have to be the same.
        """
        _GroupState = namedtuple('_GroupState',
                                 ['tenant_id', 'group_id', 'active', 'pending',
                                  'group_touched', 'policy_touched', 'paused'])
        self.assertNotEqual(
            _GroupState('tid', 'gid', {'1': {}}, {'2': {}}, 'date', {}, True),
            GroupState('tid', 'gid', {'1': {}}, {'2': {}}, 'date', {}, True))

    def test_group_touched_is_min_if_None(self):
        """
        If a group_touched of None is provided, groupTouched is
        '0001-01-01T00:00:00Z'
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, False)
        self.assertEqual(state.group_touched, '0001-01-01T00:00:00Z')

    def test_add_job_success(self):
        """
        If the job ID is not in the pending list, ``add_job`` adds it along with
        the creation time.
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, True,
                           now=lambda: 'datetime')
        state.add_job('1')
        self.assertEqual(state.pending, {'1': {'created': 'datetime'}})

    def test_add_job_fails(self):
        """
        If the job ID is in the pending list, ``add_job`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {}, {'1': {}}, None, {}, True)
        self.assertRaises(AssertionError, state.add_job, '1')
        self.assertEqual(state.pending, {'1': {}})

    def test_remove_job_success(self):
        """
        If the job ID is in the pending list, ``remove_job`` removes it.
        """
        state = GroupState('tid', 'gid', {}, {'1': {}}, None, {}, True)
        state.remove_job('1')
        self.assertEqual(state.pending, {})

    def test_remove_job_fails(self):
        """
        If the job ID is not in the pending list, ``remove_job`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, True)
        self.assertRaises(AssertionError, state.remove_job, '1')
        self.assertEqual(state.pending, {})

    def test_add_active_success_adds_creation_time(self):
        """
        If the server ID is not in the active list, ``add_active`` adds it along
        with server info, and adds the creation time to server info that
        does not already have it.
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, True,
                           now=lambda: 'datetime')
        state.add_active('1', {'stuff': 'here'})
        self.assertEqual(state.active,
                         {'1': {'stuff': 'here', 'created': 'datetime'}})

    def test_add_active_success_preserves_creation_time(self):
        """
        If the server ID is not in the active list, ``add_active`` adds it along
        with server info, and does not change the server info's creation time.
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, True,
                           now=lambda: 'other_now')
        state.add_active('1', {'stuff': 'here', 'created': 'now'})
        self.assertEqual(state.active,
                         {'1': {'stuff': 'here', 'created': 'now'}})

    def test_add_active_fails(self):
        """
        If the server ID is in the active list, ``add_active`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {'1': {}}, {}, None, {}, True)
        self.assertRaises(AssertionError, state.add_active, '1', {'1': '2'})
        self.assertEqual(state.active, {'1': {}})

    def test_remove_active_success(self):
        """
        If the server ID is in the active list, ``remove_active`` removes it.
        """
        state = GroupState('tid', 'gid', {'1': {}}, {}, None, {}, True)
        state.remove_active('1')
        self.assertEqual(state.active, {})

    def test_remove_active_fails(self):
        """
        If the server ID is not in the active list, ``remove_active`` raises an
        AssertionError.
        """
        state = GroupState('tid', 'gid', {}, {}, None, {}, True)
        self.assertRaises(AssertionError, state.remove_active, '1')
        self.assertEqual(state.active, {})

    def test_mark_executed_updates_policy_and_group(self):
        """
        Marking executed updates the policy touched and group touched to the
        same time.
        """
        t = ['0']
        state = GroupState('tid', 'gid', {}, {}, 'date', {}, True, now=t.pop)
        state.mark_executed('pid')
        self.assertEqual(state.group_touched, '0')
        self.assertEqual(state.policy_touched, {'pid': '0'})


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

    def test_modify_state_calls_modifier_with_group_and_state_and_others(self):
        """
        ``modify_state`` calls the modifier callable with the group and the
        state as the first two arguments, and the other args and keyword args
        passed to it.
        """
        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        # calling with a Deferred that never gets callbacked, because we aren't
        # testing the saving portion in this test
        modifier = mock.Mock(return_value=defer.Deferred())
        self.group.modify_state(modifier, 'arg1', kwarg1='1')
        modifier.assert_called_once_with(self.group, 'state', 'arg1', kwarg1='1')

    def test_modify_state_propagates_view_state_error(self):
        """
        ``modify_state`` should propagate a :class:`NoSuchScalingGroupError`
        that is raised by ``view_state``
        """
        self.group.view_state = mock.Mock(
            return_value=defer.fail(NoSuchScalingGroupError(1, 1)))

        modifier = mock.Mock()
        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(NoSuchScalingGroupError))
        self.assertEqual(modifier.call_count, 0)

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

    def validate_list_states_return_value(self, *args, **kwargs):
        """
        Calls ``list_scaling_group_states()`` and validates that it returns a
        list of :class:`GroupState`

        :return: the return value of ``list_scaling_group_states()``
        """
        result = self.assert_deferred_succeeded(
            self.collection.list_scaling_group_states(*args, **kwargs))

        self.assertEqual(type(result), list)
        for group in result:
            self.assertTrue(isinstance(group, GroupState))

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


class IScalingScheduleCollectionProviderMixin(DeferredTestMixin):
    """
    Mixin that tests for anything that provides
    :class:`IScalingScheduleCollection`.

    :ivar collection: an instance of the :class:`IScalingScheduleCollection` provider
    """

    def test_implements_interface(self):
        """
        The provider correctly implements
        :class:`otter.scaling_groups_interface.IScalingScheduleCollection`.
        """
        verifyObject(IScalingScheduleCollection, self.collection)

    def validate_fetch_batch_of_events(self, *args, **kwargs):
        """
        Calls ``fetch_batch_of_events()`` and validates that it returns a
        list of (tenant_id, scaling_group_id, policy_id, trigger time) tuples

        :return: the return value of ``fetch_batch_of_events()``
        """
        result = self.assert_deferred_succeeded(
            self.collection.fetch_batch_of_events(*args, **kwargs))

        self.assertEqual(type(result), list)
        for elem in result:
            self.assertEqual(type(elem), tuple)
            self.assertEqual(len(elem), 4)

        return result
