"""
Tests for :mod:`otter.models.mock`
"""
from collections import namedtuple
import json
import mock
from datetime import datetime
import iso8601

from twisted.trial.unittest import TestCase
from jsonschema import ValidationError

from otter.json_schema import group_examples

from otter.models.cass import (
    CassScalingGroup,
    CassScalingGroupCollection,
    serialize_json_data)

from otter.models.interface import (
    GroupState, GroupNotEmptyError, NoSuchScalingGroupError, NoSuchPolicyError,
    NoSuchWebhookError, UnrecognizedCapabilityError)

from otter.test.utils import LockMixin
from otter.test.models.test_interface import (
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin,
    IScalingScheduleCollectionProviderMixin)

from otter.test.utils import patch

from twisted.internet import defer
from silverberg.client import ConsistencyLevel
from silverberg.lock import BusyLockError


def _de_identify(json_obj):
    """
    >>> 'ab' == 'ab'
    True
    >>> 'ab' is 'ab'
    True

    >>> 'ab' == ' '.join(['a', 'b'])
    True
    >>> 'ab' is ' '.join(['a', 'b'])
    False

    Data coming out of cassandra will not be identical to strings that are just
    created, so this function is a way to a mock JSON object not identical to
    a re-creation the same object, or its keys/values not identical to an
    expected string.
    """
    if json_obj is not None:
        return json.loads(json.dumps(json_obj))


def _cassandrify_data(list_of_dicts):
    """
    To make mocked up test data less verbose, produce what cassandra would
    return from a list of dictionaries.  So for instance, passing the following:

        [{'policyId': 'group1', 'data': '{}'},
         {'policyId': 'group2', 'data': '{}'}]

    would return:

        {'cols': [{'timestamp': None, 'name': 'policyId',
                   'value': 'group1', 'ttl': None},
                  {'timestamp': None, 'name': 'data',
                   'value': '{}', 'ttl': None}], 'key': ''},
        {'cols': [{'timestamp': None, 'name': 'policyId',
                   'value': 'group3', 'ttl': None},
                  {'timestamp': None, 'name': 'data',
                   'value': '{}', 'ttl': None}], 'key': ''}]

    This function also de-identifies the data for you.
    """
    return _de_identify(list_of_dicts)


class SerialJsonDataTestCase(TestCase):
    """
    Serializing json data to be put into cassandra should append a version
    """
    def test_adds_version_that_is_provided(self):
        """
        The key "_ver" is be added to whatever dictionary is there with the
        value being whatever is provided
        """
        self.assertEqual(serialize_json_data({}, 'version'),
                         json.dumps({'_ver': 'version'}))


class DummyException(Exception):
    """
    Specific exception class, to be used in testing exception handling
    """


class CassScalingGroupTestCase(IScalingGroupProviderMixin, LockMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.connection = mock.MagicMock(spec=['execute'])

        self.returns = [None]

        def _responses(*args):
            result = _de_identify(self.returns.pop(0))
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.tenant_id = '11111'
        self.group_id = '12345678g'
        self.config = _de_identify({
            'name': 'a',
            'cooldown': 0,
            'minEntities': 0
        })
        # this is the config with all the default vals
        self.output_config = _de_identify({
            'name': 'a',
            'cooldown': 0,
            'minEntities': 0,
            'maxEntities': None,
            'metadata': {}
        })
        self.launch_config = _de_identify({
            "type": "launch_server",
            "args": {"server": {"these are": "some args"}}
        })
        self.policies = []
        self.mock_log = mock.MagicMock()
        self.group = CassScalingGroup(self.mock_log, self.tenant_id,
                                      self.group_id,
                                      self.connection)

        self.mock_key = patch(self, 'otter.models.cass.generate_key_str',
                              return_value='12345678')
        self.mock_capability = patch(self, 'otter.models.cass.generate_capability',
                                     return_value=('ver', 'hash'))

        patch(self, 'otter.models.cass.get_consistency_level',
              return_value=ConsistencyLevel.TWO)

        self.lock = self.mock_lock()
        patch(self, 'otter.models.cass.BasicLock', return_value=self.lock)

    def test_view_config(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [[{'data': '{}'}]]
        d = self.group.view_config()
        r = self.successResultOf(d)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_state(self):
        """
        Test that you can call view state and receive a valid parsed response
        """
        cass_response = _cassandrify_data([
            {'tenantId': self.tenant_id, 'groupId': self.group_id,
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x00'}])

        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        expectedCql = ('SELECT "tenantId", "groupId", active, pending, '
                       '"groupTouched", "policyTouched", paused FROM group_state '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       {'A': 'R'}, {'P': 'R'}, '123',
                                       {'PT': 'R'}, False))

    def test_view_state_no_such_group(self):
        """
        Calling ``view_state`` on a group that doesn't exist raises a
        ``NoSuchScalingGroupError``
        """
        self.returns = [[]]
        d = self.group.view_state()
        f = self.failureResultOf(d)
        self.assertTrue(f.check(NoSuchScalingGroupError))

    def test_view_paused_state(self):
        """
        view_state returns a dictionary with a key paused equal to True for a
        paused group.
        """
        cass_response = _cassandrify_data([
            {'tenantId': self.tenant_id, 'groupId': self.group_id,
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x01'}])

        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       {'A': 'R'}, {'P': 'R'}, '123',
                                       {'PT': 'R'}, True))

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_succeeds(self, mock_serial):
        """
        ``modify_state`` writes the state the modifier returns to the database
        """
        def modifier(group, state):
            return GroupState(self.tenant_id, self.group_id, {}, {}, None, {}, True)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.assertEqual(self.successResultOf(d), None)
        expectedCql = (
            'INSERT INTO group_state("tenantId", "groupId", active, '
            'pending, "groupTouched", "policyTouched", paused) VALUES('
            ':tenantId, :groupId, :active, :pending, :groupTouched, '
            ':policyTouched, :paused);')

        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id,
                        "active": _S({}), "pending": _S({}),
                        "groupTouched": '0001-01-01T00:00:00Z',
                        "policyTouched": _S({}),
                        "paused": True}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

        self.lock.acquire.assert_called_once_with()
        self.lock.release.assert_called_once_with()

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_lock_not_acquired(self, mock_serial):
        """
        ``modify_state`` writes the state the modifier returns to the database
        """
        def acquire():
            return defer.fail(BusyLockError('', ''))
        self.lock.acquire.side_effect = acquire

        def modifier(group, state):
            raise

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        result = self.failureResultOf(d)
        self.assertTrue(result.check(BusyLockError))

        self.assertEqual(self.connection.execute.call_count, 0)
        self.lock.acquire.assert_called_once_with()
        self.assertEqual(self.lock.release.call_count, 0)

    def test_modify_state_propagates_modifier_error_and_does_not_save(self):
        """
        ``modify_state`` does not write anything to the db if the modifier
        raises an exception
        """
        def modifier(group, state):
            raise NoSuchScalingGroupError(self.tenant_id, self.group_id)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(NoSuchScalingGroupError))
        self.assertEqual(self.connection.execute.call_count, 0)

    def test_modify_state_asserts_error_if_tenant_id_mismatch(self):
        """
        ``modify_state`` raises an :class:`AssertionError` if the tenant id
        of the :class:`GroupState` returned by the modifier does not match its
        tenant id
        """
        def modifier(group, state):
            return GroupState('tid', self.group_id, {}, {}, None, {}, True)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(AssertionError))
        self.assertEqual(self.connection.execute.call_count, 0)

    def test_modify_state_asserts_error_if_group_id_mismatch(self):
        """
        ``modify_state`` raises an :class:`AssertionError` if the group id
        of the :class:`GroupState` returned by the modifier does not match its
        group id
        """
        def modifier(group, state):
            return GroupState(self.tenant_id, 'gid', {}, {}, None, {}, True)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(AssertionError))
        self.assertEqual(self.connection.execute.call_count, 0)

    def test_view_config_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_view_config_no_version(self):
        """
        When viewing the config, any version information is removed from the
        final output
        """
        cass_response = [{'data': '{"_ver": 5}'}]
        self.returns = [cass_response]
        d = self.group.view_config()
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    def test_view_launch(self):
        """
        Test that you can call view and receive a valid parsed response
        for the launch config
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.successResultOf(d)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_launch_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_view_launch_no_version(self):
        """
        When viewing the launch config, any version information is removed from
        the final output
        """
        cass_response = [{'data': '{"_ver": 5}'}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    def test_update_config(self):
        """
        Test that you can update a config, and if its successful the return
        value is None
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response, None]
        d = self.group.update_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", "groupId", data) VALUES '
                       '(:tenantId, :groupId, :scaling) APPLY BATCH;')
        expectedData = {"scaling": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_launch(self):
        """
        Test that you can update a launch config, and if successful the return
        value is None
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response, None]
        d = self.group.update_launch_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = ('BEGIN BATCH INSERT INTO launch_config("tenantId", "groupId", data) VALUES '
                       '(:tenantId, :groupId, :launch) APPLY BATCH;')
        expectedData = {"launch": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_configs_call_view_first(self):
        """
        When updating a config or launch config, `view_config` is called first
        and if it fails, the rest of the update does not continue
        """
        updates = [
            lambda: self.group.update_config({'b': 'lah'}),
            lambda: self.group.update_launch_config({'b': 'lah'})
        ]

        for callback in updates:
            self.group.view_config = mock.MagicMock(
                return_value=defer.fail(DummyException('boo')))
            self.assert_deferred_failed(callback(), DummyException)

            # view is called
            self.group.view_config.assert_called_once_with()
            # but extra executes, to update, are not called
            self.assertFalse(self.connection.execute.called)

    def test_view_policy(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444")
        r = self.successResultOf(d)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g", "policyId": "3444"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_policy_no_such_policy(self):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.get_policy('3444')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g", "policyId": "3444"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_view_policy_no_version(self):
        """
        When viewing the policy, any version information is removed from the
        final output
        """
        cass_response = [{'data': '{"_ver": 5}'}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444")
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    def test_naive_list_policies_with_policies(self):
        """
        Naive list policies lists existing scaling policies
        """
        self.returns = [[
            {'policyId': 'policy1', 'data': '{}'},
            {'policyId': 'policy2', 'data': '{}'}]]

        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111'}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        d = self.group._naive_list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, {'policy1': {}, 'policy2': {}})

        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    def test_naive_list_policies_with_no_policies(self, mock_view_config):
        """
        Naive list policies returns an empty list if there are no policies
        whether or not there is a scaling group (does not check view_config)
        """
        self.returns = [[]]
        d = self.group._naive_list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, {})
        self.assertEqual(len(mock_view_config.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    def test_list_policies_with_policies(self, mock_naive, mock_view_config):
        """
        List policies calls naive list policies, and doesn't call view config
        if there are existing policies
        """
        expected_result = {'policy1': {}, 'policy2': {}}
        mock_naive.return_value = defer.succeed(expected_result)

        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with()
        self.assertEqual(len(mock_view_config.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed({}))
    def test_list_policy_empty_list_existing_group(self, mock_naive,
                                                   mock_view_config):
        """
        List policies calls naive list policies, and calls view config if
        there are no existing policies.  Return value is the empty list if
        view config doesn't raise an error.
        """
        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, {})

        mock_naive.assert_called_once_with()
        mock_view_config.assert_called_with()

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed({}))
    def test_list_policy_invalid_group(self, mock_naive, mock_view_config):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingGroupError`
        """
        self.assert_deferred_failed(self.group.list_policies(),
                                    NoSuchScalingGroupError)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_list_policy_no_version(self):
        """
        When listing the policies, any version information is removed from the
        final output
        """
        cass_response = [{'policyId': 'group1', 'data': '{"_ver": 5}'},
                         {'policyId': 'group3', 'data': '{"_ver": 2}'}]
        self.returns = [cass_response]
        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, {'group1': {}, 'group3': {}})

    def test_add_scaling_policy(self):
        """
        Test that you can add a scaling policy, and what is returned is a
        dictionary of the ids to the scaling policies
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response, None]
        d = self.group.create_policies([{"b": "lah"}])
        result = self.successResultOf(d)
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
                       'data) VALUES (:tenantId, :groupId, :policy0Id, :policy0) '
                       'APPLY BATCH;')
        expectedData = {"policy0": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "policy0Id": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        self.assertEqual(result, {self.mock_key.return_value: {'b': 'lah'}})

    def test_add_scaling_policy_at(self):
        """
        Test that you can add a scaling policy with 'at' schedule and what is returned is
        dictionary of the ids to the scaling policies
        """
        cass_response = [{'data': '{}'}]
        self.returns = [cass_response, None]
        expected_at = '2012-10-20T03:23:45'

        pol = {'cooldown': 5, 'type': 'schedule', 'name': 'scale up by 10', 'change': 10,
               'args': {'at': '2012-10-20T03:23:45'}}
        d = self.group.create_policies([pol])
        result = self.successResultOf(d)
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
                       'data) VALUES (:tenantId, :groupId, :policy0Id, :policy0) '
                       'INSERT INTO scaling_schedule("tenantId", "groupId", "policyId", trigger) '
                       'VALUES (:tenantId, :groupId, :policy0Id, :policy0Trigger) '
                       'APPLY BATCH;')
        expectedData = {"policy0": ('{"name": "scale up by 10", "args": {"at": "2012-10-20T03:23:45"}, '
                                    '"cooldown": 5, "_ver": 1, "type": "schedule", "change": 10}'),
                        "groupId": '12345678g',
                        "policy0Id": '12345678',
                        "policy0Trigger": iso8601.parse_date(expected_at),
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        self.assertEqual(result, {self.mock_key.return_value: pol})

    def test_add_first_checks_view_config(self):
        """
        Before a policy is added, `view_config` is first called to determine
        that there is such a scaling group
        """
        self.group.view_config = mock.MagicMock(return_value=defer.succeed({}))
        self.returns = [None]
        d = self.group.create_policies([{"b": "lah"}])
        self.successResultOf(d)
        self.group.view_config.assert_called_once_with()

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_delete_policy_valid_policy(self, mock_get_policy):
        """
        When you delete a scaling policy, it checks if the policy exists and
        if it does, deletes the policy and all its associated webhooks.
        """
        d = self.group.delete_policy('3222')
        # delete returns None
        self.assertIsNone(self.successResultOf(d))
        mock_get_policy.assert_called_once_with('3222')

        expected_cql = (
            'BEGIN BATCH '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND '
            '"groupId" = :groupId AND "policyId" = :policyId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND '
            '"groupId" = :groupId AND "policyId" = :policyId '
            'DELETE FROM scaling_schedule WHERE "policyId" = :policyId; '
            'APPLY BATCH;')
        expected_data = {
            "tenantId": self.group.tenant_id,
            "groupId": self.group.uuid,
            "policyId": "3222"}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    def test_delete_policy_invalid_policy(self, mock_get_policy):
        """
        When you delete a scaling policy that doesn't exist, a
        :class:`NoSuchPolicyError` is raised
        """
        d = self.group.delete_policy('3222')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        mock_get_policy.assert_called_once_with('3222')
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_scaling_policy(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        cass_response = [{'data': '{"type": "helvetica"}'}]
        self.returns = [cass_response, None]
        d = self.group.update_policy('12345678', {"b": "lah", "type": "helvetica"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
            'VALUES (:tenantId, :groupId, :policyId, :policy) APPLY BATCH;')
        expectedData = {"policy": '{"_ver": 1, "b": "lah", "type": "helvetica"}',
                        "groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy_schedule_no_change(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        cass_response = [{'data': '{"type": "schedule", "args": {"ott": "er"}}'}]
        self.returns = [cass_response, None]
        d = self.group.update_policy('12345678', {"b": "lah", "type": "schedule", "args": {"ott": "er"}})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
            'VALUES (:tenantId, :groupId, :policyId, :policy) APPLY BATCH;')
        expectedData = {"policy": '{"_ver": 1, "b": "lah", "type": "schedule", "args": {"ott": "er"}}',
                        "groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy_type_change(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        cass_response = [{'data': '{"type": "helvetica"}'}]
        self.returns = [cass_response, None]
        d = self.group.update_policy('12345678', {"b": "lah", "type": "comicsans"})
        self.assert_deferred_failed(d, ValidationError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy_schedule_change(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        cass_response = [{'data': '{"type": "schedule", "args": {"ott":"er"}}'}]
        self.returns = [cass_response, None]
        d = self.group.update_policy('12345678', {"b": "lah", "type": "schedule", "args": {"y": "arrr"}})
        self.assert_deferred_failed(d, ValidationError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy_bad(self):
        """
        Tests that if you try to update a scaling policy that doesn't exist, the right thing happens
        """
        self.returns = [[], None]
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_config_bad(self):
        """
        Tests that you can't just create a scaling group by sending
        an update to a nonexistant group
        """
        self.returns = [[], None]
        d = self.group.update_config({"b": "lah"})
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_update_policy_calls_view_first(self):
        """
        When updating a policy, a `get_policy` is called first and if it fails,
        the rest of the update does not continue
        """
        self.group.get_policy = mock.MagicMock(
            return_value=defer.fail(DummyException("Cassandra failure")))
        self.assert_deferred_failed(self.group.update_policy('1', {'b': 'lah'}),
                                    DummyException)

        # view is called
        self.group.get_policy.assert_called_once_with('1')
        # but extra executes, to update, are not called
        self.assertFalse(self.connection.execute.called)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_add_webhooks_valid_policy_check_return_value(self, mock_get_policy):
        """
        When adding one or more webhooks is successful, what is returned is a
        dictionary of the webhook ids to the webhooks, which include capability
        info and metadata.
        """
        mock_ids = ['100001', '100002']

        def _return_uuid(*args, **kwargs):
            return mock_ids.pop(0)

        self.mock_key.side_effect = _return_uuid
        self.returns = [None]
        result = self.validate_create_webhooks_return_value(
            '23456789',
            [{'name': 'a name'}, {'name': 'new name', 'metadata': {"k": "v"}}])

        capability = {"hash": 'hash', "version": 'ver'}
        expected_results = {
            '100001': {'name': 'a name',
                       'metadata': {},
                       'capability': capability},
            '100002': {'name': 'new name',
                       'metadata': {"k": "v"},
                       'capability': capability}
        }

        self.assertEqual(result, dict(expected_results))

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_add_webhooks_valid_policy_check_query(self, mock_get_policy):
        """
        When adding one or more webhooks is successful, what is returned is a
        dictionary of the webhook ids to the webhooks, which include capability
        info and metadata.
        """
        mock_ids = ['100001', '100002']

        def _return_uuid(*args, **kwargs):
            return mock_ids.pop(0)

        self.mock_key.side_effect = _return_uuid
        self.returns = [None]

        self.validate_create_webhooks_return_value(
            '23456789',
            [{'name': 'a name'}, {'name': 'new name', 'metadata': {'k': 'v'}}])

        expected_cql = (
            'BEGIN BATCH '
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", "webhookId", '
            'data, capability, "webhookKey") VALUES (:tenantId, :groupId, :policyId, '
            ':webhook0Id, :webhook0, :webhook0Capability, :webhook0Key) '
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", "webhookId", '
            'data, capability, "webhookKey") VALUES (:tenantId, :groupId, :policyId, '
            ':webhook1Id, :webhook1, :webhook1Capability, :webhook1Key) '
            'APPLY BATCH;')

        # can't test the parameters, because they contain serialized JSON.
        # have to pull out the serialized JSON, load it as an object, and then
        # compare
        self.connection.execute.assert_called_with(
            expected_cql, mock.ANY, ConsistencyLevel.TWO)

        cql_params = self.connection.execute.call_args[0][1]

        for name in ('webhook0', 'webhook1'):
            cql_params[name] = json.loads(cql_params[name])
            capability_name = '{0}Capability'.format(name)
            cql_params[capability_name] = json.loads(cql_params[capability_name])

        expected_params = {
            "tenantId": '11111',
            "groupId": '12345678g',
            "policyId": '23456789',
            "webhook0Id": '100001',
            "webhook0": {'name': 'a name', 'metadata': {}, '_ver': 1},
            "webhook0Capability": {"ver": "hash", "_ver": 1},
            "webhook0Key": "hash",
            "webhook1Id": '100002',
            "webhook1": {'name': 'new name', 'metadata': {'k': 'v'}, '_ver': 1},
            "webhook1Capability": {"ver": "hash", "_ver": 1},
            "webhook1Key": "hash"
        }

        self.assertEqual(cql_params, expected_params)

    def test_add_webhooks_invalid_policy(self):
        """
        Can't add webhooks to an invalid policy.
        """
        self.returns = [[], None]
        d = self.group.create_webhooks('23456789', [{}, {'metadata': 'who'}])
        self.assert_deferred_failed(d, NoSuchPolicyError)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    def test_naive_list_webhooks_valid_policy(self, mock_get_policy):
        """
        Naive list webhooks produces a valid dictionary as per
        :data:`otter.json_schema.model_schemas.webhook_list`, whether or not
        the policy is invalid
        """
        expected_data = {'name': 'name', 'metadata': {}}
        data = json.dumps(expected_data)
        capability = '{"ver": "hash"}'
        self.returns = [_cassandrify_data([
            {'webhookId': 'webhook1', 'data': data, 'capability': capability},
            {'webhookId': 'webhook2', 'data': data, 'capability': capability}
        ])]

        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policyId": '23456789'}
        expectedCql = ('SELECT "webhookId", data, capability FROM '
                       'policy_webhooks WHERE "tenantId" = :tenantId AND '
                       '"groupId" = :groupId AND "policyId" = :policyId;')
        r = self.successResultOf(
            self.group._naive_list_webhooks('23456789'))

        expected_data['capability'] = {
            "version": "ver",
            "hash": "hash"
        }

        self.assertEqual(r, {'webhook1': expected_data,
                             'webhook2': expected_data})
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    def test_naive_list_webhooks_empty_list(self, mock_get_policy):
        """
        If there are no webhooks, list webhooks produces an empty dictionary
        even if the policy were invalid
        """
        self.returns = [[]]
        r = self.successResultOf(
            self.group._naive_list_webhooks('23456789'))
        self.assertEqual(r, {})
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks')
    def test_list_webhooks_valid_policy(self, mock_naive, mock_get_policy):
        """
        Listing a valid policy calls ``naive_list_webhooks``, and skips calling
        ``get_policy`` since there are undeleted webhooks for said policy
        """
        expected_webhook_data = {'name': 'name', 'metadata': {}}
        expected_webhook_data['capability'] = {
            'version': 'ver',
            'hash': 'hash'
        }
        expected_result = {
            'webhook1': expected_webhook_data,
            'webhook2': expected_webhook_data
        }
        mock_naive.return_value = defer.succeed(expected_result)
        r = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with('23456789')
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed({}))
    def test_list_webhooks_empty_list(self, mock_naive, mock_get_policy):
        """
        Listing a valid policy calls ``naive_list_webhooks``, and then calls
        ``get_policy`` to see if the policy actually exists
        """
        result = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(result, {})

        mock_naive.assert_called_with('23456789')
        mock_get_policy.assert_called_once_with('23456789')

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'p', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed({}))
    def test_list_webhooks_invalid_policy(self, mock_naive, mock_get_policy):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingPolicy`
        """
        self.assert_deferred_failed(self.group.list_webhooks('23456789'),
                                    NoSuchPolicyError)
        mock_naive.assert_called_with('23456789')
        mock_get_policy.assert_called_once_with('23456789')
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_view_webhook(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [_cassandrify_data(
            [{'data': '{"name": "pokey"}', 'capability': '{"1": "h"}'}])]
        d = self.group.get_webhook("3444", "4555")
        r = self.successResultOf(d)
        expectedCql = ('SELECT data, capability FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND "webhookId" = :webhookId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g",
                        "policyId": "3444", "webhookId": "4555"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(
            r, {'name': 'pokey', 'capability': {"version": "1", "hash": "h"}})

    def test_view_webhook_no_such_webhook(self):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        self.returns = [[]]
        d = self.group.get_webhook('3444', '4555')
        self.assert_deferred_failed(d, NoSuchWebhookError)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_view_webhook_no_version(self):
        """
        When viewing the policy, any version information is removed from the
        final output
        """
        self.returns = [_cassandrify_data([{'data': '{"_ver": 5}'}])]
        d = self.group.get_policy("3444")
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    @mock.patch('otter.models.cass.CassScalingGroup.get_webhook')
    def test_update_webhook(self, mock_get_webhook):
        """
        You can update an existing webhook, and it would overwrite all data
        """
        mock_get_webhook.return_value = defer.succeed(
            {'name': 'name', 'metadata': {'old': 'metadata'}})
        self.returns = [None]

        new_webhook_data = {
            'name': 'newname',
            'metadata': {'new': 'metadata'}
        }

        d = self.group.update_webhook('3444', '4555', new_webhook_data)
        self.assertIsNone(self.successResultOf(d))

        expectedCql = (
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", '
            '"webhookId", data) VALUES (:tenantId, :groupId, :policyId, '
            ':webhookId, :data);')

        # json is serialized, so unserialize it and check
        self.connection.execute.assert_called_once_with(
            expectedCql, mock.ANY, ConsistencyLevel.TWO)

        # first call, args
        data = self.connection.execute.call_args[0][1]
        data['data'] = json.loads(data['data'])
        new_webhook_data['_ver'] = 1
        self.assertEqual(data,
                         {"tenantId": "11111", "groupId": "12345678g",
                          "policyId": "3444", "webhookId": "4555",
                          "data": new_webhook_data})

    @mock.patch('otter.models.cass.CassScalingGroup.get_webhook')
    def test_update_webhook_default_empty_metadata(self, mock_get_webhook):
        """
        You can update an existing webhook, and if new metadata is not provided
        a default empty dict will be assigned to the new metadata
        """
        mock_get_webhook.return_value = defer.succeed(
            {'name': 'name', 'metadata': {'old': 'metadata'}})
        self.returns = [None]

        d = self.group.update_webhook('3444', '4555', {'name': 'newname'})
        self.assertIsNone(self.successResultOf(d))

        self.assertEqual(
            json.loads(self.connection.execute.call_args[0][1]['data']),
            {'name': 'newname', 'metadata': {}, '_ver': 1})

    @mock.patch('otter.models.cass.CassScalingGroup.get_webhook',
                return_value=defer.fail(NoSuchWebhookError('t', 'g', 'p', 'w')))
    def test_update_webhook_invalid_webhook(self, mock_get_webhook):
        """
        Updating a webhook that does not exist returns a
        class:`NoSuchWebhookError` failure, and no update is attempted
        """
        d = self.group.update_webhook('3444', '4555', {'name': 'aname'})
        self.assert_deferred_failed(d, NoSuchWebhookError)
        self.assertEqual(len(self.connection.execute.mock_calls), 0)
        self.flushLoggedErrors(NoSuchWebhookError)

    def test_delete_webhook(self):
        """
        Tests that you can delete a scaling policy webhook, and if successful
        return value is None
        """
        # return values for get webhook and then delete
        self.returns = [
            _cassandrify_data([{'data': '{}', 'capability': '{"1": "h"}'}]),
            None]
        d = self.group.delete_webhook('3444', '4555')
        self.assertIsNone(self.successResultOf(d))  # delete returns None
        expectedCql = ('DELETE FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND "webhookId" = :webhookId')
        expectedData = {"tenantId": "11111", "groupId": "12345678g",
                        "policyId": "3444", "webhookId": "4555"}

        self.assertEqual(len(self.connection.execute.mock_calls), 2)  # view, delete
        self.connection.execute.assert_called_with(expectedCql,
                                                   expectedData,
                                                   ConsistencyLevel.TWO)

    def test_delete_non_existant_webhooks(self):
        """
        If you try to delete a scaling policy webhook that doesn't exist,
        :class:`NoSuchWebhookError` is raised
        """
        self.returns = [[], None]
        d = self.group.delete_webhook('3444', '4555')
        self.assert_deferred_failed(d, NoSuchWebhookError)
        self.assertEqual(len(self.connection.execute.mock_calls), 1)  # only view
        self.flushLoggedErrors(NoSuchWebhookError)

    def test_view_manifest_success(self):
        """
        When viewing the manifest, if the group exists a dictionary with the
        config, launch config, and scaling policies is returned.
        """
        self.group.view_config = mock.MagicMock(
            return_value=defer.succeed(self.config))
        self.group.view_launch_config = mock.MagicMock(
            return_value=defer.succeed(self.launch_config))
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed({}))

        self.assertEqual(self.validate_view_manifest_return_value(),
                         {'groupConfiguration': self.config,
                          'launchConfiguration': self.launch_config,
                          'scalingPolicies': {},
                          'id': "12345678g"})
        self.group.view_config.assert_called_once_with()
        self.group.view_launch_config.assert_called_once_with()
        self.group._naive_list_policies.assert_called_once_with()

    def test_view_manifest_no_such_group(self):
        """
        When viewing the manifest, if the group doesn't exist (and hence there
        is no config), the ``NoSuchScalingGroup`` error that is raised by
        ``view_config`` is propagated up and viewing the launch config and the
        policies is never done.
        """
        self.group.view_config = mock.MagicMock(
            return_value=defer.fail(NoSuchScalingGroupError('1', '1')))
        self.group.view_launch_config = mock.MagicMock(
            return_value=defer.succeed('launch config'))
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed('policies'))

        self.assert_deferred_failed(self.group.view_manifest(),
                                    NoSuchScalingGroupError)
        self.group.view_config.assert_called_once_with()
        self.assertEqual(len(self.group.view_launch_config.mock_calls), 0)
        self.assertEqual(len(self.group._naive_list_policies), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_non_empty_scaling_group_fails(self, mock_view_state):
        """
        ``delete_group`` errbacks with :class:`GroupNotEmptyError` if scaling
        group state is not empty
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, {'1': {}}, {}, None, {}, False))
        self.assert_deferred_failed(self.group.delete_group(), GroupNotEmptyError)

        # nothing else called except view
        self.assertTrue(mock_view_state.called)
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(GroupNotEmptyError)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    def test_delete_empty_scaling_group_with_policies(self, mock_naive,
                                                      mock_view_state):
        """
        ``delete_group`` deletes config, launch config, state, and the group's
        policies and webhooks and events if the scaling group is empty.
        It uses naive list policies to figure out what events to delete.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed({'policyA': {}, 'policyB': {}})

        self.returns = [None]
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id,
                         'policyid0': 'policyA',
                         'policyid1': 'policyB'}
        expected_cql = (
            'BEGIN BATCH '
            'DELETE FROM scaling_config WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM launch_config WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM group_state WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM scaling_schedule WHERE "policyId" IN (:policyid0,:policyid1) '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

        self.lock.acquire.assert_called_once_with()
        self.lock.release.assert_called_once_with()

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    def test_delete_empty_scaling_group_with_zero_policies(self, mock_naive,
                                                           mock_view_state):
        """
        ``delete_group`` deletes config, launch config, state, and the group's
        policies and webhooks but not events if the scaling group is empty but
        has no policies.
        It uses naive list policies to figure out what events to delete.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed({})

        self.returns = [None]
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id}
        expected_cql = (
            'BEGIN BATCH '
            'DELETE FROM scaling_config WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM launch_config WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM group_state WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

        self.lock.acquire.assert_called_once_with()
        self.lock.release.assert_called_once_with()

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_not_acquired(self, mock_view_state):
        """
        If the lock is not acquired, do not delete the group.
        """
        def acquire():
            return defer.fail(BusyLockError('', ''))
        self.lock.acquire.side_effect = acquire

        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, {}, {}, None, {}, False))

        d = self.group.delete_group()
        result = self.failureResultOf(d)
        self.assertTrue(result.check(BusyLockError))

        self.assertEqual(self.connection.execute.call_count, 0)
        self.lock.acquire.assert_called_once_with()


# wrapper for serialization mocking - 'serialized' things will just be wrapped
# with this
_S = namedtuple('_S', ['thing'])


class CassScalingScheduleCollectionTestCase(IScalingScheduleCollectionProviderMixin,
                                            TestCase):
    """
    Tests for :class:`CassScalingScheduleCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock(spec=['execute'])

        self.returns = [None]

        def _responses(*args):
            result = _de_identify(self.returns.pop(0))
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.collection = CassScalingGroupCollection(self.connection)
        patch(self, 'otter.models.cass.get_consistency_level',
              return_value=ConsistencyLevel.TWO)

    def test_fetch(self):
        """
        Tests that you can fetch a list of events
        """
        self.returns = [_cassandrify_data(
            [{'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ef', 'trigger': 100},
             {'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ex', 'trigger': 122}])]

        expectedData = {'now': 1234, 'size': 100}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId", "trigger" FROM scaling_schedule '
                       'WHERE trigger <= :now LIMIT :size ALLOW FILTERING;')

        result = self.validate_fetch_batch_of_events(1234, 100)
        self.assertEqual(result, [('1d2', 'gr2', 'ef', 100),
                                  ('1d2', 'gr2', 'ex', 122)])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_delete_events(self):
        """
        Tests that you can delete event of a given policy_ids
        """
        expectedData = {'policyid0': 'p1', 'policyid1': 'p2'}
        expectedCql = 'DELETE FROM scaling_schedule WHERE "policyId" IN (:policyid0,:policyid1);'
        result = self.successResultOf(self.collection.delete_events(['p1', 'p2']))
        self.assertEqual(result, None)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_update_events_trigger(self):
        """
        Tests that you can update trigger times of one or more policies
        """
        datetime0 = datetime(2012, 10, 20, 5, 24, 31)
        datetime1 = datetime(2012, 10, 22, 7, 20, 30)
        expectedData = {
            'trigger0': datetime0,
            'policyid0': 'p1',
            'trigger1': datetime1,
            'policyid1': 'p2'}
        expectedCql = ('BEGIN BATCH '
                       'UPDATE scaling_schedule SET trigger = :trigger0 '
                       'WHERE "policyId" = :policyid0; '
                       'UPDATE scaling_schedule SET trigger = :trigger1 '
                       'WHERE "policyId" = :policyid1; '
                       'APPLY BATCH;')
        d = self.collection.update_events_trigger([('p1', datetime0),
                                                   ('p2', datetime1)])
        self.assertEqual(self.successResultOf(d), None)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)


class CassScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`CassScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock(spec=['execute'])

        self.returns = [None]

        def _responses(*args):
            result = _de_identify(self.returns.pop(0))
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.mock_log = mock.MagicMock()

        self.collection = CassScalingGroupCollection(self.connection)
        self.tenant_id = 'goo1234'
        self.config = _de_identify({
            'name': 'blah',
            'cooldown': 600,
            'minEntities': 0,
            'maxEntities': 10,
            'metadata': {}
        })
        self.launch = _de_identify(group_examples.launch_server_config()[0])

        self.mock_key = patch(self, 'otter.models.cass.generate_key_str')
        patch(self, 'otter.models.cass.get_consistency_level',
              return_value=ConsistencyLevel.TWO)

        # 'serializing' something just wraps it with a _S
        self.mock_serial = patch(self, 'otter.models.cass.serialize_json_data',
                                 side_effect=lambda *args: _S(args[0]))

    def test_create(self):
        """
        Test that you can create a group, and if successful the group ID is
        returned
        """
        expectedData = {
            'scaling': _S(self.config),
            'launch': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123'}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, '
                       ':scaling) INSERT INTO launch_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, :launch) '
                       'INSERT INTO group_state("tenantId", "groupId", active, pending, '
                       '"policyTouched", paused) VALUES(:tenantId, :groupId, \'{}\', '
                       '\'{}\', \'{}\', False) APPLY BATCH;')
        self.mock_key.return_value = '12345678'

        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch)
        self.assertEqual(result, {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': {},
            'id': self.mock_key.return_value
        })
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_create_with_policy(self):
        """
        Test that you can create a scaling group with a single policy, and if
        successful the group ID is returned
        """
        policy = group_examples.policy()[0]

        expectedData = {
            'scaling': _S(self.config),
            'launch': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123',
            'policy0Id': '12345678',
            'policy0': _S(policy)}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, '
                       ':scaling) INSERT INTO launch_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, :launch) '
                       'INSERT INTO group_state("tenantId", "groupId", active, pending, '
                       '"policyTouched", paused) VALUES(:tenantId, :groupId, \'{}\', '
                       '\'{}\', \'{}\', False) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
                       'VALUES (:tenantId, :groupId, :policy0Id, :policy0) '
                       'APPLY BATCH;')
        self.mock_key.return_value = '12345678'
        policy = group_examples.policy()[0]
        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch,
                                                   [policy])
        self.assertEqual(result, {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': {self.mock_key.return_value: policy},
            'id': self.mock_key.return_value
        })
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_create_with_policy_multiple(self):
        """
        Test that you can create a scaling group with multiple policies, and if
        successful the group ID is returned
        """
        policies = group_examples.policy()[:2]

        expectedData = {
            'scaling': _S(self.config),
            'launch': _S(self.launch),
            'groupId': '1',
            'tenantId': '123',
            'policy0Id': '2',
            'policy0': _S(policies[0]),
            'policy1Id': '3',
            'policy1': _S(policies[1])}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, '
                       ':scaling) INSERT INTO launch_config("tenantId", '
                       '"groupId", data) VALUES (:tenantId, :groupId, :launch) '
                       'INSERT INTO group_state("tenantId", "groupId", active, pending, '
                       '"policyTouched", paused) VALUES(:tenantId, :groupId, \'{}\', '
                       '\'{}\', \'{}\', False) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
                       'VALUES (:tenantId, :groupId, :policy0Id, :policy0) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
                       'VALUES (:tenantId, :groupId, :policy1Id, :policy1) '
                       'APPLY BATCH;')

        counter = [0]

        def mock_key_gen(*args, **kwargs):
            counter[0] += 1
            return str(counter[0])

        self.mock_key.side_effect = mock_key_gen
        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch,
                                                   policies)
        self.assertEqual(result, {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': dict(zip(('2', '3'), policies)),
            'id': '1'
        })
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_states(self):
        """
        ``list_scaling_group_states`` returns a list of :class:`GroupState`
        objects from cassandra
        """
        self.returns = [_cassandrify_data([{
            'tenantId': '123',
            'groupId': 'group{}'.format(i),
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00'
        } for i in range(2)])]

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "tenantId", "groupId", active, pending, '
                       '"groupTouched", "policyTouched", paused FROM '
                       'group_state WHERE "tenantId" = :tenantId;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, [
            GroupState('123', 'group0', {}, {}, '0001-01-01T00:00:00Z', {}, False),
            GroupState('123', 'group1', {}, {}, '0001-01-01T00:00:00Z', {}, False)])

    def test_list_empty(self):
        """
        If there are no states in cassandra, ``list_scaling_group_states``
        returns an empty list
        """
        self.returns = [[]]

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "tenantId", "groupId", active, pending, '
                       '"groupTouched", "policyTouched", paused FROM '
                       'group_state WHERE "tenantId" = :tenantId;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(r, [])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_get_scaling_group(self):
        """
        Tests that you can get a scaling group
        (note that it doesn't request the database)
        """
        g = self.collection.get_scaling_group(self.mock_log, '123', '12345678')
        self.assertTrue(isinstance(g, CassScalingGroup))
        self.assertEqual(g.uuid, '12345678')
        self.assertEqual(g.tenant_id, '123')

    def test_webhook_hash(self):
        """
        Test that you can get webhook info by hash.
        """
        self.returns = [_cassandrify_data([
            {'tenantId': '123', 'groupId': 'group1', 'policyId': 'pol1'}]),
            _cassandrify_data([{'data': '{}'}])
        ]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId" FROM policy_webhooks WHERE '
                       '"webhookKey" = :webhookKey;')
        d = self.collection.webhook_info_by_hash(self.mock_log, 'x')
        r = self.successResultOf(d)
        self.assertEqual(r, ('123', 'group1', 'pol1'))
        self.connection.execute.assert_called_any(expectedCql,
                                                  expectedData,
                                                  ConsistencyLevel.TWO)

        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expectedData = {"tenantId": "123", "groupId": "group1", "policyId": "pol1"}
        self.connection.execute.assert_called_any(expectedCql,
                                                  expectedData,
                                                  ConsistencyLevel.TWO)

    def test_webhook_bad(self):
        """
        Test that a bad webhook will fail predictably
        """
        self.returns = [[]]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId" FROM policy_webhooks WHERE '
                       '"webhookKey" = :webhookKey;')
        d = self.collection.webhook_info_by_hash(self.mock_log, 'x')
        self.assert_deferred_failed(d, UnrecognizedCapabilityError)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_get_counts(self):
        """
        Check get_count returns dictionary in proper format
        """
        self.returns = [
            [{'count': 100}],
            [{'count': 101}],
            [{'count': 102}],
        ]

        expectedData = {'tenantId': '123'}
        expectedResults = {
            "groups": 100,
            "policies": 101,
            "webhooks": 102
        }
        config_query = ('SELECT COUNT(*) FROM scaling_config WHERE "tenantId" = :tenantId;')
        policy_query = ('SELECT COUNT(*) FROM scaling_policies WHERE "tenantId" = :tenantId;')
        webhook_query = ('SELECT COUNT(*) FROM policy_webhooks WHERE "tenantId" = :tenantId;')

        calls = [mock.call(config_query, expectedData, ConsistencyLevel.TWO),
                 mock.call(policy_query, expectedData, ConsistencyLevel.TWO),
                 mock.call(webhook_query, expectedData, ConsistencyLevel.TWO)]

        d = self.collection.get_counts(self.mock_log, '123')
        result = self.successResultOf(d)
        self.assertEquals(result, expectedResults)
        self.connection.execute.assert_has_calls(calls)
