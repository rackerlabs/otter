"""
Tests for :mod:`otter.models.mock`
"""
from collections import namedtuple
import json
import mock
from datetime import datetime
import itertools

from twisted.trial.unittest import TestCase
from jsonschema import ValidationError

from otter.json_schema import group_examples

from otter.models.cass import (
    CassScalingGroup,
    CassScalingGroupCollection,
    CassAdmin,
    serialize_json_data,
    get_consistency_level,
    verified_view)

from otter.models.interface import (
    GroupState, GroupNotEmptyError, NoSuchScalingGroupError, NoSuchPolicyError,
    NoSuchWebhookError, UnrecognizedCapabilityError, ScalingGroupOverLimitError,
    WebhooksOverLimitError, PoliciesOverLimitError)

from otter.test.utils import LockMixin, DummyException, mock_log
from otter.test.models.test_interface import (
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin,
    IScalingScheduleCollectionProviderMixin)

from otter.test.utils import patch, matches
from testtools.matchers import IsInstance, ContainsDict, Equals
from otter.util.timestamp import from_timestamp
from otter.util.config import set_config_data

from twisted.internet import defer
from twisted.internet.task import Clock
from silverberg.client import ConsistencyLevel
from kazoo.protocol.states import KazooState


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


class GetConsistencyTests(TestCase):
    """
    Tests for `get_consistency_level`
    """
    def test_unknown_resource(self):
        """
        When called with unknown resource it returns ConsistencyLevel.ONE
        """
        level = get_consistency_level('list', 'junk')
        self.assertEqual(level, ConsistencyLevel.ONE)

    def test_unknown_operation(self):
        """
        When called with unknown operation it returns ConsistencyLevel.ONE
        """
        level = get_consistency_level('junk', 'event')
        self.assertEqual(level, ConsistencyLevel.ONE)

    def test_unknown_operation_and_resource(self):
        """
        When called with unknown operation and resource it returns ConsistencyLevel.ONE
        """
        level = get_consistency_level('junk', 'junk2')
        self.assertEqual(level, ConsistencyLevel.ONE)

    def test_event_fetch(self):
        """
        Gives QUORUM on event fetch
        """
        level = get_consistency_level('fetch', 'event')
        self.assertEqual(level, ConsistencyLevel.QUORUM)

    def test_group_create(self):
        """
        Gives QUORUM on group create
        """
        level = get_consistency_level('create', 'group')
        self.assertEqual(level, ConsistencyLevel.QUORUM)

    def test_update_state(self):
        """
        Gives QUORUM on updating state
        """
        level = get_consistency_level('update', 'state')
        self.assertEqual(level, ConsistencyLevel.QUORUM)


class VerifiedViewTests(TestCase):
    """
    Tests for `verified_view`
    """

    def setUp(self):
        """
        mock connection object
        """
        self.connection = mock.MagicMock(spec=['execute'])
        self.log = mock_log()

    def test_valid_view(self):
        """
        Returns row if it is valid
        """
        self.connection.execute.return_value = defer.succeed([{'c1': 2, 'created_at': 23}])
        r = verified_view(self.connection, 'vq', 'dq', {'d': 2}, 6, ValueError, self.log)
        self.assertEqual(self.successResultOf(r), {'c1': 2, 'created_at': 23})
        self.connection.execute.assert_called_once_with('vq', {'d': 2}, 6)
        self.assertFalse(self.log.msg.called)

    def test_resurrected_view(self):
        """
        Raise empty error if resurrected view
        """
        self.connection.execute.return_value = defer.succeed([{'c1': 2, 'created_at': None}])
        r = verified_view(self.connection, 'vq', 'dq', {'d': 2}, 6, ValueError, self.log)
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_has_calls([mock.call('vq', {'d': 2}, 6),
                                                  mock.call('dq', {'d': 2}, 6)])
        self.log.msg.assert_called_once_with('Resurrected row', row={'c1': 2, 'created_at': None},
                                             row_params={'d': 2})

    def test_del_does_not_wait(self):
        """
        When a resurrected row is encountered it is triggered for deletion and `verified_view`
        does not wait for its result before returning
        """
        first_time = [True]

        def _execute(*args):
            if first_time[0]:
                first_time[0] = False
                return defer.succeed([{'c1': 2, 'created_at': None}])
            return defer.Deferred()

        self.connection.execute.side_effect = _execute
        r = verified_view(self.connection, 'vq', 'dq', {'d': 2}, 6, ValueError, self.log)
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_has_calls([mock.call('vq', {'d': 2}, 6),
                                                  mock.call('dq', {'d': 2}, 6)])

    def test_empty_view(self):
        """
        Raise empty error if no result
        """
        self.connection.execute.return_value = defer.succeed([])
        r = verified_view(self.connection, 'vq', 'dq', {'d': 2}, 6, ValueError, self.log)
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_called_once_with('vq', {'d': 2}, 6)
        self.assertFalse(self.log.msg.called)


class CassScalingGroupTestCase(IScalingGroupProviderMixin, LockMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.connection = mock.MagicMock(spec=['execute'])
        set_config_data({'limits': {'absolute': {'maxWebhooksPerPolicy': 1000}}})
        self.addCleanup(set_config_data, {})

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
        self.launch_config = _de_identify(group_examples.launch_server_config()[0])
        self.policies = []
        self.mock_log = mock.MagicMock()

        self.kz_lock = mock.Mock()
        self.lock = self.mock_lock()
        self.kz_lock.Lock.return_value = self.lock

        self.group = CassScalingGroup(self.mock_log, self.tenant_id,
                                      self.group_id,
                                      self.connection, itertools.cycle(range(2, 10)),
                                      self.kz_lock)
        self.mock_log.bind.assert_called_once_with(system='CassScalingGroup',
                                                   tenant_id=self.tenant_id,
                                                   scaling_group_id=self.group_id)
        self.mock_log = self.mock_log.bind()

        self.mock_key = patch(self, 'otter.models.cass.generate_key_str',
                              return_value='12345678')
        self.mock_capability = patch(self, 'otter.models.cass.generate_capability',
                                     return_value=('ver', 'hash'))

        patch(self, 'otter.models.cass.get_consistency_level',
              return_value=ConsistencyLevel.TWO)

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

        self.mock_next_cron_occurrence = patch(
            self, 'otter.models.cass.next_cron_occurrence', return_value='next_time')


class CassScalingGroupTests(CassScalingGroupTestCase):
    """
    CassScalingGroup's tests
    """

    def test_view_config(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [[{'group_config': '{}', 'created_at': 24}]]
        d = self.group.view_config()
        r = self.successResultOf(d)
        expectedCql = ('SELECT group_config, created_at FROM scaling_group WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_config_recurrected_entry(self):
        """
        If group row returned is resurrected, i.e. does not have 'created_at', then
        NoSuchScalingGroupError is returned and that row's deletion is triggered
        """
        self.returns = [[{'group_config': '{}', 'created_at': None}], None]
        r = self.group.view_config()
        self.failureResultOf(r, NoSuchScalingGroupError)
        view_cql = ('SELECT group_config, created_at FROM scaling_group WHERE '
                    '"tenantId" = :tenantId AND "groupId" = :groupId;')
        del_cql = ('DELETE FROM scaling_group WHERE '
                   '"tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_has_calls(
            [mock.call(view_cql, expectedData, ConsistencyLevel.TWO),
             mock.call(del_cql, expectedData, ConsistencyLevel.TWO)])

    def test_view_state(self):
        """
        Test that you can call view state and receive a valid parsed response
        """
        cass_response = [
            {'tenantId': self.tenant_id, 'groupId': self.group_id, 'group_config': '{"name": "a"}',
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x00', 'created_at': 23}]
        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM scaling_group '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a', {'A': 'R'},
                                       {'P': 'R'}, '123', {'PT': 'R'}, False))

    def test_view_respsects_consistency_argument(self):
        """
        If a consistency argument is passed to ``view_state``, it is honored
        over the default consistency
        """
        cass_response = [
            {'tenantId': self.tenant_id, 'groupId': self.group_id, 'group_config': '{"name": "a"}',
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x00', 'created_at': 23}]
        self.returns = [cass_response]
        d = self.group.view_state(consistency=ConsistencyLevel.ALL)
        self.successResultOf(d)
        self.connection.execute.assert_called_once_with(mock.ANY,
                                                        mock.ANY,
                                                        ConsistencyLevel.ALL)

    def test_view_state_no_such_group(self):
        """
        Calling ``view_state`` on a group that doesn't exist raises a
        ``NoSuchScalingGroupError``
        """
        self.returns = [[]]
        d = self.group.view_state()
        f = self.failureResultOf(d)
        self.assertTrue(f.check(NoSuchScalingGroupError))

    def test_view_state_recurrected_entry(self):
        """
        If group row returned is resurrected, i.e. does not have 'created_at', then
        NoSuchScalingGroupError is returned and that row's deletion is triggered
        """
        cass_response = [
            {'tenantId': self.tenant_id, 'groupId': self.group_id, 'group_config': '{"name": "a"}',
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x00', 'created_at': None}]
        self.returns = [cass_response, None]
        d = self.group.view_state()
        self.failureResultOf(d, NoSuchScalingGroupError)
        viewCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                   '"groupTouched", "policyTouched", paused, created_at FROM scaling_group '
                   'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        delCql = ('DELETE FROM scaling_group '
                  'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.connection.execute.assert_has_calls(
            [mock.call(viewCql, expectedData, ConsistencyLevel.TWO),
             mock.call(delCql, expectedData, ConsistencyLevel.TWO)])

    def test_view_paused_state(self):
        """
        view_state returns a dictionary with a key paused equal to True for a
        paused group.
        """
        cass_response = _cassandrify_data([
            {'tenantId': self.tenant_id, 'groupId': self.group_id, 'group_config': '{"name": "a"}',
             'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
             'policyTouched': '{"PT":"R"}', 'paused': '\x01', 'created_at': 3}])

        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a', {'A': 'R'}, {'P': 'R'},
                                       '123', {'PT': 'R'}, True))

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_succeeds(self, mock_serial):
        """
        ``modify_state`` writes the state the modifier returns to the database
        """
        def modifier(group, state):
            return GroupState(self.tenant_id, self.group_id, 'a', {}, {}, None, {}, True)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.assertEqual(self.successResultOf(d), None)
        self.group.view_state.assert_called_once_with(ConsistencyLevel.TWO)
        expectedCql = (
            'INSERT INTO scaling_group("tenantId", "groupId", active, '
            'pending, "groupTouched", "policyTouched", paused) VALUES('
            ':tenantId, :groupId, :active, :pending, :groupTouched, '
            ':policyTouched, :paused)')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id,
                        "active": _S({}), "pending": _S({}),
                        "groupTouched": '0001-01-01T00:00:00Z',
                        "policyTouched": _S({}),
                        "paused": True}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

        self.kz_lock.Lock.assert_called_once_with('/locks/' + self.group.uuid)

        self.lock._acquire.assert_called_once_with(timeout=120)
        self.lock.release.assert_called_once_with()

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_lock_not_acquired(self, mock_serial):
        """
        ``modify_state`` raises error if lock is not acquired and does not
        do anything else
        """
        self.lock.acquire.side_effect = lambda timeout: defer.fail(ValueError('a'))

        def modifier(group, state):
            raise

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.failureResultOf(d, ValueError)

        self.assertEqual(self.connection.execute.call_count, 0)
        self.kz_lock.Lock.assert_called_once_with('/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        self.assertEqual(self.lock.release.call_count, 0)

    def test_modify_state_lock_log_category_locking(self):
        """
        `modify_state` locking logs with category='locking'
        """
        def modifier(group, state):
            return GroupState(self.tenant_id, self.group_id, 'a', {}, {}, None, {}, True)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        self.returns = [None, None]
        log = self.group.log = mock.Mock()

        self.group.modify_state(modifier)

        log.bind.assert_called_once_with(system='CassScalingGroup.modify_state')
        log.bind().bind.assert_called_once_with(category='locking')
        self.assertEqual(log.bind().bind().msg.call_count, 2)

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
            return GroupState('tid', self.group_id, 'name', {}, {}, None, {}, True)

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
            return GroupState(self.tenant_id, 'gid', 'name', {}, {}, None, {}, True)

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
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT group_config, created_at FROM scaling_group WHERE '
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
        cass_response = [{'group_config': '{"_ver": 5}', 'created_at': 23}]
        self.returns = [cass_response]
        d = self.group.view_config()
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    def test_view_launch(self):
        """
        Test that you can call view and receive a valid parsed response
        for the launch config
        """
        cass_response = [{'launch_config': '{}', 'created_at': 23}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.successResultOf(d)
        expectedCql = ('SELECT launch_config, created_at FROM scaling_group WHERE '
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
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT launch_config, created_at FROM scaling_group WHERE '
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
        cass_response = [{'launch_config': '{"_ver": 5}', 'created_at': 3}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    @mock.patch('otter.models.cass.verified_view')
    def test_view_launch_resurrected_entry(self, mock_verfied_view):
        """
        When viewing the launch config, if the returned row is rescurrected row, it
        is not returned and it is triggerred for deletion
        """
        mock_verfied_view.return_value = defer.fail(NoSuchScalingGroupError('a', 'b'))
        d = self.group.view_launch_config()
        self.failureResultOf(d, NoSuchScalingGroupError)
        viewCql = ('SELECT launch_config, created_at FROM scaling_group WHERE '
                   '"tenantId" = :tenantId AND "groupId" = :groupId;')
        delCql = ('DELETE FROM scaling_group WHERE '
                  '"tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        mock_verfied_view.assert_called_once_with(self.connection, viewCql, delCql,
                                                  expectedData, ConsistencyLevel.TWO,
                                                  matches(IsInstance(NoSuchScalingGroupError)),
                                                  self.mock_log)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_config(self, view_config):
        """
        Test that you can update a config, and if its successful the return
        value is None
        """
        d = self.group.update_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = ('BEGIN BATCH '
                       'INSERT INTO scaling_group("tenantId", "groupId", group_config) '
                       'VALUES (:tenantId, :groupId, :scaling) '
                       'APPLY BATCH;')
        expectedData = {"scaling": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_launch(self, view_config):
        """
        Test that you can update a launch config, and if successful the return
        value is None
        """
        d = self.group.update_launch_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = ('BEGIN BATCH '
                       'INSERT INTO scaling_group("tenantId", "groupId", launch_config) '
                       'VALUES (:tenantId, :groupId, :launch) '
                       'APPLY BATCH;')
        expectedData = {"launch": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config')
    def test_update_configs_call_view_first(self, view_config):
        """
        When updating a config or launch config, `view_config` is called first
        and if it fails, the rest of the update does not continue
        """
        updates = [
            lambda: self.group.update_config({'b': 'lah'}),
            lambda: self.group.update_launch_config({'b': 'lah'})
        ]

        for i, callback in enumerate(updates):
            view_config.return_value = defer.fail(DummyException('boo'))
            self.failureResultOf(callback(), DummyException)

            # view is called
            self.assertEqual(view_config.call_count, i + 1)
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
        expectedCql = ('SELECT data, version FROM scaling_policies WHERE "tenantId" = :tenantId '
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
        self.failureResultOf(d, NoSuchPolicyError)
        expectedCql = ('SELECT data, version FROM scaling_policies WHERE "tenantId" = :tenantId '
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

    def test_view_policy_with_version_success(self):
        """
        Calling `get_policy` with version succeeds if version matches
        """
        cass_response = [{'data': '{"_ver": 5}', 'version': 'v1'}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444", version='v1')
        r = self.successResultOf(d)
        self.assertEqual(r, {})

    def test_view_policy_with_version_fails(self):
        """
        Calling `get_policy` with version fails if version does not match
        """
        cass_response = [{'data': '{"_ver": 5}', 'version': 'v1'}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444", version='v2')
        self.failureResultOf(d, NoSuchPolicyError)
        self.flushLoggedErrors(NoSuchPolicyError)

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
        self.assertEqual(r, [{'id': 'policy1'}, {'id': 'policy2'}])

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
        self.assertEqual(r, [])
        self.assertEqual(len(mock_view_config.mock_calls), 0)

    def test_naive_list_policies_respects_limit(self):
        """
        If there are more than the requested number of policies,
        ``_naive_list_policies`` only requests the requested number.
        """
        cass_response = [{'policyId': 'policy1', 'data': '{"_ver": 5}'},
                         {'policyId': 'policy2', 'data': '{"_ver": 2}'}]
        self.returns = [cass_response]
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "limit": 2}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
                       'LIMIT :limit;')
        d = self.group._naive_list_policies(limit=2)
        r = self.successResultOf(d)
        self.assertEqual(r, [{'id': 'policy1'}, {'id': 'policy2'}])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_naive_list_policies_offsets_by_marker(self):
        """
        If a marker is provided, it is passed into the CQL as a where clause
        """
        cass_response = [{'policyId': 'policy1', 'data': '{"_ver": 5}'},
                         {'policyId': 'policy2', 'data': '{"_ver": 2}'}]
        self.returns = [cass_response]
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "limit": 2,
                        "marker": 'blah'}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
                       'AND "policyId" > :marker LIMIT :limit;')
        d = self.group._naive_list_policies(limit=2, marker="blah")
        r = self.successResultOf(d)
        self.assertEqual(r, [{'id': 'policy1'}, {'id': 'policy2'}])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    def test_list_policies_with_policies(self, mock_naive, mock_view_config):
        """
        List policies calls naive list policies, and doesn't call view config
        if there are existing policies
        """
        expected_result = [{'id': 'policy1'}, {'id': 'policy2'}]
        mock_naive.return_value = defer.succeed(expected_result)

        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with(limit=100, marker=None)
        self.assertEqual(len(mock_view_config.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed([]))
    def test_list_policy_empty_list_existing_group(self, mock_naive,
                                                   mock_view_config):
        """
        List policies calls naive list policies, and calls view config if
        there are no existing policies.  Return value is the empty list if
        view config doesn't raise an error.
        """
        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, [])

        mock_naive.assert_called_once_with(limit=100, marker=None)
        mock_view_config.assert_called_with()

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    def test_list_policies_passes_limit_and_marker(self, mock_naive, _):
        """
        List policies calls ``naive_list_policies`` with the appropriate limit
        and marker values
        """
        expected_result = [{'id': 'policy1'}, {'id': 'policy2'}]
        mock_naive.return_value = defer.succeed(expected_result)

        d = self.group.list_policies(limit=5, marker='blah')
        r = self.successResultOf(d)
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with(limit=5, marker='blah')

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed([]))
    def test_list_policy_invalid_group(self, mock_naive, mock_view_config):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingGroupError`
        """
        self.failureResultOf(self.group.list_policies(),
                             NoSuchScalingGroupError)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_list_policy_no_version(self):
        """
        When listing the policies, any version information is removed from the
        final output
        """
        cass_response = [{'policyId': 'policy1', 'data': '{"_ver": 5}'},
                         {'policyId': 'policy3', 'data': '{"_ver": 2}'}]
        self.returns = [cass_response]
        d = self.group.list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, [{'id': 'policy1'}, {'id': 'policy3'}])

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
        self.failureResultOf(d, NoSuchPolicyError)
        mock_get_policy.assert_called_once_with('3222')
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_config_bad(self):
        """
        Tests that you can't just create a scaling group by sending
        an update to a nonexistant group
        """
        self.returns = [[], None]
        d = self.group.update_config({"b": "lah"})
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT group_config, created_at FROM scaling_group WHERE '
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
        self.failureResultOf(self.group.update_policy('1', {'b': 'lah'}),
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
        list of the webhooks with ids, which include capability info and
        metadata.
        """
        mock_ids = ['100001', '100002']

        def _return_uuid(*args, **kwargs):
            return mock_ids.pop(0)

        self.mock_key.side_effect = _return_uuid
        self.returns = [[{'count': 0}], None]
        result = self.validate_create_webhooks_return_value(
            '23456789',
            [{'name': 'a name'}, {'name': 'new name', 'metadata': {"k": "v"}}])

        capability = {"hash": 'hash', "version": 'ver'}
        expected_results = [
            {'id': '100001',
             'name': 'a name',
             'metadata': {},
             'capability': capability},
            {'id': '100002',
             'name': 'new name',
             'metadata': {"k": "v"},
             'capability': capability}
        ]

        self.assertEqual(result, expected_results)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_add_webhooks_valid_policy_check_query(self, mock_get_policy):
        """
        When adding one or more webhooks is successful, what is returned is a
        list of the webhooks with ids, which include capability info and
        metadata.
        """
        mock_ids = ['100001', '100002']

        def _return_uuid(*args, **kwargs):
            return mock_ids.pop(0)

        self.mock_key.side_effect = _return_uuid
        self.returns = [[{'count': 0}], None]
        policy_id = '23456789'

        self.validate_create_webhooks_return_value(
            policy_id,
            [{'name': 'a name'}, {'name': 'new name', 'metadata': {'k': 'v'}}])

        expected_count_cql = (
            'SELECT COUNT(*) FROM policy_webhooks WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_params = {'tenantId': self.tenant_id, 'groupId': self.group_id,
                           'policyId': policy_id}

        expected_insert_cql = (
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
        self.assertEqual(
            self.connection.execute.mock_calls,
            [mock.call(expected_count_cql, expected_params,
                       ConsistencyLevel.TWO),
             mock.call(expected_insert_cql, mock.ANY, ConsistencyLevel.TWO)])

        cql_params = self.connection.execute.call_args[0][1]

        for name in ('webhook0', 'webhook1'):
            cql_params[name] = json.loads(cql_params[name])
            capability_name = '{0}Capability'.format(name)
            cql_params[capability_name] = json.loads(cql_params[capability_name])

        expected_params.update({
            "webhook0Id": '100001',
            "webhook0": {'name': 'a name', 'metadata': {}, '_ver': 1},
            "webhook0Capability": {"ver": "hash", "_ver": 1},
            "webhook0Key": "hash",
            "webhook1Id": '100002',
            "webhook1": {'name': 'new name', 'metadata': {'k': 'v'}, '_ver': 1},
            "webhook1Capability": {"ver": "hash", "_ver": 1},
            "webhook1Key": "hash"
        })

        self.assertEqual(cql_params, expected_params)

    def test_add_webhooks_invalid_policy(self):
        """
        Can't add webhooks to an invalid policy.
        """
        self.returns = [[]]
        d = self.group.create_webhooks('23456789', [{}, {'metadata': 'who'}])
        self.failureResultOf(d, NoSuchPolicyError)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_add_webhooks_already_beyond_limits(self, _):
        """
        Can't add a webhook if already at limit
        """
        policy_id = '23456789'
        self.returns = [[{'count': 1000}], None]
        d = self.group.create_webhooks(policy_id, [{}])
        self.failureResultOf(d, WebhooksOverLimitError)

        expected_cql = (
            'SELECT COUNT(*) FROM policy_webhooks WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id,
                         'policyId': policy_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    def test_add_many_webhooks_beyond_limits(self, _):
        """
        Can't add any of the webhooks if adding all would bring it above the
        limit
        """
        policy_id = '23456789'
        self.returns = [[{'count': 990}], None]
        d = self.group.create_webhooks(policy_id, [{} for i in range(20)])
        self.failureResultOf(d, WebhooksOverLimitError)

        expected_cql = (
            'SELECT COUNT(*) FROM policy_webhooks WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id,
                         'policyId': policy_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    def test_naive_list_webhooks_valid_policy(self, mock_get_policy):
        """
        Naive list webhooks produces a valid list as per
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
                        "policyId": '23456789',
                        "limit": 100}
        expectedCql = ('SELECT "webhookId", data, capability FROM '
                       'policy_webhooks WHERE "tenantId" = :tenantId AND '
                       '"groupId" = :groupId AND "policyId" = :policyId '
                       'LIMIT :limit;')
        r = self.successResultOf(
            self.group._naive_list_webhooks('23456789', 100, None))

        expected_data['capability'] = {
            "version": "ver",
            "hash": "hash"
        }

        self.assertEqual(r, [dict(id='webhook1', **expected_data),
                             dict(id='webhook2', **expected_data)])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    def test_naive_list_webhooks_empty_list(self, mock_get_policy):
        """
        If there are no webhooks, list webhooks produces an empty list
        even if the policy were invalid
        """
        self.returns = [[]]
        r = self.successResultOf(
            self.group._naive_list_webhooks('23456789', 2, None))
        self.assertEqual(r, [])
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    def test_naive_list_webhooks_respects_limit(self):
        """
        The limit provided is passed to the CQL query
        """
        self.returns = [[]]
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policyId": '234567',
                        "limit": 2}
        expectedCql = ('SELECT "webhookId", data, capability FROM '
                       'policy_webhooks WHERE "tenantId" = :tenantId AND '
                       '"groupId" = :groupId AND "policyId" = :policyId '
                       'LIMIT :limit;')
        d = self.group._naive_list_webhooks('234567', 2, None)
        r = self.successResultOf(d)
        self.assertEqual(r, [])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_naive_list_webhooks_offsets_by_marker(self):
        """
        If a marker is provided, it is passed into the CQL as a where clause
        """
        expected_data = {'name': 'name', 'metadata': {}}
        data = json.dumps(expected_data)
        capability = '{"ver": "hash"}'
        self.returns = [[
            {'webhookId': 'webhook1', 'data': data, 'capability': capability}
        ]]
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policyId": '234567',
                        "limit": 2,
                        "marker": 'blah'}
        expectedCql = ('SELECT "webhookId", data, capability FROM '
                       'policy_webhooks WHERE "tenantId" = :tenantId AND '
                       '"groupId" = :groupId AND "policyId" = :policyId '
                       'AND "webhookId" > :marker LIMIT :limit;')
        d = self.group._naive_list_webhooks('234567', 2, "blah")
        expected_data['capability'] = {
            "version": "ver",
            "hash": "hash"
        }
        r = self.successResultOf(d)
        self.assertEqual(r, [dict(id='webhook1', **expected_data)])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

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
        expected_result = [
            dict(id='webhook1', **expected_webhook_data),
            dict(id='webhook2', **expected_webhook_data)
        ]
        mock_naive.return_value = defer.succeed(expected_result)
        r = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with('23456789', limit=100, marker=None)
        self.assertEqual(len(mock_get_policy.mock_calls), 0)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed([]))
    def test_list_webhooks_empty_list(self, mock_naive, mock_get_policy):
        """
        Listing a valid policy calls ``naive_list_webhooks``, and then calls
        ``get_policy`` to see if the policy actually exists
        """
        result = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(result, [])

        mock_naive.assert_called_with('23456789', limit=100, marker=None)
        mock_get_policy.assert_called_once_with('23456789')

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'p', 'g')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed([]))
    def test_list_webhooks_invalid_policy(self, mock_naive, mock_get_policy):
        """
        If the group does not exist, `list_webhooks` raises a
        :class:`NoSuchScalingPolicy`
        """
        self.failureResultOf(self.group.list_webhooks('23456789'),
                             NoSuchPolicyError)
        mock_naive.assert_called_with('23456789', limit=100, marker=None)
        mock_get_policy.assert_called_once_with('23456789')
        self.flushLoggedErrors(NoSuchPolicyError)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks')
    def test_list_webhooks_passes_limit_and_marker(self, mock_naive, _):
        """
        List webhooks calls ``naive_list_webhooks`` with the appropriate limit
        and marker values
        """
        expected_result = [{'id': 'webhook1'}, {'id': 'webhook2'}]
        mock_naive.return_value = defer.succeed(expected_result)

        d = self.group.list_webhooks('1234', limit=5, marker='blah')
        r = self.successResultOf(d)
        self.assertEqual(r, expected_result)

        mock_naive.assert_called_once_with('1234', limit=5, marker='blah')

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
        self.failureResultOf(d, NoSuchWebhookError)
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
        self.failureResultOf(d, NoSuchWebhookError)
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
        self.failureResultOf(d, NoSuchWebhookError)
        self.assertEqual(len(self.connection.execute.mock_calls), 1)  # only view
        self.flushLoggedErrors(NoSuchWebhookError)

    @mock.patch('otter.models.cass.config_value', return_value=10)
    @mock.patch('otter.models.cass.verified_view')
    def test_view_manifest_success(self, verified_view, _):
        """
        When viewing the manifest, if the group exists a dictionary with the
        config, launch config, and scaling policies is returned.
        """
        verified_view.return_value = defer.succeed({
            'tenantId': self.tenant_id, "groupId": self.group_id,
            'id': "12345678g", 'group_config': serialize_json_data(self.config, 1.0),
            'launch_config': serialize_json_data(self.launch_config, 1.0),
            'active': '{"A":"R"}', 'pending': '{"P":"R"}', 'groupTouched': '123',
            'policyTouched': '{"PT":"R"}', 'paused': '\x00', 'created_at': 23
        })
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed([]))

        self.assertEqual(self.validate_view_manifest_return_value(), {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch_config,
            'scalingPolicies': [],
            'id': "12345678g",
            'state': GroupState(
                self.tenant_id,
                self.group_id,
                'a', {'A': 'R'},
                {'P': 'R'}, '123',
                {'PT': 'R'}, False)
        })

        self.group._naive_list_policies.assert_called_once_with(limit=10)

        view_cql = ('SELECT "tenantId", "groupId", group_config, launch_config, active, '
                    'pending, "groupTouched", "policyTouched", paused, created_at '
                    'FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        del_cql = 'DELETE FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId'
        exp_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}
        verified_view.assert_called_once_with(self.connection, view_cql, del_cql,
                                              exp_data, ConsistencyLevel.TWO,
                                              matches(IsInstance(NoSuchScalingGroupError)),
                                              self.mock_log)

    @mock.patch('otter.models.cass.verified_view',
                return_value=defer.fail(NoSuchScalingGroupError(2, 3)))
    def test_view_manifest_no_such_group(self, verified_view):
        """
        When viewing the manifest, if the group doesn't exist ``NoSuchScalingGroupError``
        is raised and the policies is never retreived.
        """
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed('policies'))

        self.failureResultOf(self.group.view_manifest(), NoSuchScalingGroupError)
        self.flushLoggedErrors()
        self.assertFalse(self.group._naive_list_policies.called)

    def test_view_manifest_resurrected_entry(self):
        """
        If returned view is resurrected, i.e. that does not contain 'created_at',
        then it is triggered for deletion and NoSuchScalingGroupError is raised
        """
        # This may not be required since verified_view call is checked in
        # test_view_manifest_success
        select_return = [{'group_config': serialize_json_data(self.config, 1.0),
                          'launch_config': serialize_json_data(self.launch_config, 1.0)}]
        self.returns = [select_return, None]
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed({}))
        r = self.group.view_manifest()
        self.failureResultOf(r, NoSuchScalingGroupError)
        view_cql = ('SELECT "tenantId", "groupId", group_config, launch_config, active, '
                    'pending, "groupTouched", "policyTouched", paused, created_at '
                    'FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        del_cql = 'DELETE FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId'
        exp_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}
        self.connection.execute.assert_has_calls(
            [mock.call(view_cql, exp_data, ConsistencyLevel.TWO),
             mock.call(del_cql, exp_data, ConsistencyLevel.TWO)])

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_non_empty_scaling_group_fails(self, mock_view_state):
        """
        ``delete_group`` errbacks with :class:`GroupNotEmptyError` if scaling
        group state is not empty
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {'1': {}}, {}, None, {}, False))
        self.failureResultOf(self.group.delete_group(), GroupNotEmptyError)

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
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed(
            [{'id': 'policyA'}, {'id': 'policyB'}])

        self.returns = [None]
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id}
        expected_cql = (
            'BEGIN BATCH '
            'DELETE FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

        self.kz_lock.Lock.assert_called_once_with('/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
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
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed({})

        self.returns = [None]
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id}
        expected_cql = (
            'BEGIN BATCH '
            'DELETE FROM scaling_group WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

        self.kz_lock.Lock.assert_called_once_with('/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        self.lock.release.assert_called_once_with()

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_not_acquired(self, mock_view_state):
        """
        If the lock is not acquired, do not delete the group.
        """
        self.lock.acquire.side_effect = lambda timeout: defer.fail(ValueError('a'))

        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, 'a', {}, {}, None, {}, False))

        d = self.group.delete_group()
        self.failureResultOf(d, ValueError)

        self.assertFalse(self.connection.execute.called)
        self.kz_lock.Lock.assert_called_once_with('/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_with_log_category_locking(self, mock_view_state):
        """
        The lock is created with log with category as locking
        """
        log = self.group.log = mock.Mock()

        self.group.delete_group()

        log.bind.assert_called_once_with(system='CassScalingGroup.delete_group')
        log.bind().bind.assert_called_once_with(category='locking')
        self.assertEqual(log.bind().bind().msg.call_count, 2)


class CassScalingGroupUpdatePolicyTests(CassScalingGroupTestCase):
    """
    Tests for `ScalingGroup.update_policy`
    """

    def setUp(self):
        """
        Mock `get_policy`
        """
        super(CassScalingGroupUpdatePolicyTests, self).setUp()
        self.get_policy = patch(self, 'otter.models.cass.CassScalingGroup.get_policy')

    def validate_policy_update(self, policy_json):
        """
        Validate CQL calls made to update the policy
        """
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '
            'APPLY BATCH;')
        expectedData = {"data": policy_json,
                        "groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111',
                        "version": "timeuuid"}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed({"type": "helvetica"})
        d = self.group.update_policy('12345678', {"b": "lah", "type": "helvetica"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        self.validate_policy_update('{"_ver": 1, "b": "lah", "type": "helvetica"}')

    def test_update_scaling_policy_schedule_no_change(self):
        """
        Schedule policy update with no args difference also updates scaling_schedule_v2 table.
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed({"type": "schedule",
                                                      "args": {"cron": "1 * * * *"}})
        d = self.group.update_policy('12345678', {"type": "schedule",
                                                  "args": {"cron": "1 * * * *"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, cron, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, :cron, :version) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '
            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"cron": "1 * * * *"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g', "policyId": '12345678',
            "tenantId": '11111', "trigger": "next_time",
            "version": 'timeuuid', "bucket": 2, "cron": '1 * * * *'}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    def test_update_scaling_policy_type_change(self):
        """
        Policy type cannot be changed while updating it
        """
        self.get_policy.return_value = defer.succeed({"type": "helvetica"})
        d = self.group.update_policy('12345678', {"b": "lah", "type": "comicsans"})
        self.failureResultOf(d, ValidationError)
        self.assertFalse(self.connection.execute.called)

    def test_update_scaling_policy_at_schedule_change(self):
        """
        Updating at-style schedule policy updates respective entry in
        scaling_schedule_v2 table also
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed({"type": "schedule",
                                                      "args": {"at": "2013-07-30T19:03:12Z"}})
        d = self.group.update_policy('12345678', {"type": "schedule",
                                                  "args": {"at": "2015-09-20T10:00:12Z"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, :version) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '
            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"at": "2015-09-20T10:00:12Z"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g', "policyId": '12345678',
            "tenantId": '11111', "trigger": from_timestamp("2015-09-20T10:00:12Z"),
            "version": 'timeuuid', "bucket": 2}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    def test_update_scaling_policy_cron_schedule_change(self):
        """
        Updating cron-style schedule policy updates respective entry in
        scaling_schedule_v2 table also
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed({"type": "schedule",
                                                      "args": {"cron": "1 * * * *"}})
        d = self.group.update_policy('12345678', {"type": "schedule",
                                                  "args": {"cron": "2 0 * * *"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, cron, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, :cron, :version) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '
            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"cron": "2 0 * * *"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g', "policyId": '12345678',
            "tenantId": '11111', "trigger": "next_time",
            "version": 'timeuuid', "bucket": 2, "cron": '2 0 * * *'}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    def test_update_scaling_policy_bad(self):
        """
        Tests that if you try to update a scaling policy that doesn't exist, the right thing happens
        """
        self.get_policy.return_value = defer.fail(NoSuchPolicyError('t', 'g', 'p'))
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.failureResultOf(d, NoSuchPolicyError)
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(NoSuchPolicyError)


# wrapper for serialization mocking - 'serialized' things will just be wrapped
# with this
_S = namedtuple('_S', ['thing'])


class ScalingGroupAddPoliciesTests(CassScalingGroupTestCase):
    """
    Tests for `CassScalingGroup.create_policies`
    """

    def setUp(self):
        """
        Mock view_config
        """
        super(ScalingGroupAddPoliciesTests, self).setUp()
        self.view_config = patch(self, 'otter.models.cass.CassScalingGroup.view_config',
                                 return_value=defer.succeed({}))
        set_config_data({'limits': {'absolute': {'maxPoliciesPerGroup': 1000}}})
        self.addCleanup(set_config_data, {})

    def test_add_one_policy_overlimit(self):
        """
        If current policies is at max policies, fail with
        PoliciesOverLimitError
        """
        self.returns = [[{'count': 1000}]]
        d = self.group.create_policies([{"b": "lah"}])
        self.failureResultOf(d, PoliciesOverLimitError)

        expected_cql = (
            'SELECT COUNT(*) FROM scaling_policies WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    def test_add_multiple_policies_overlimit(self):
        """
        If current policies + new policies will go over max policies, fail with
        PoliciesOverLimitError
        """
        self.returns = [[{'count': 998}]]
        d = self.group.create_policies([{"b": "lah"}] * 5)
        self.failureResultOf(d, PoliciesOverLimitError)

        expected_cql = (
            'SELECT COUNT(*) FROM scaling_policies WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    def test_add_first_checks_view_config(self):
        """
        Before a policy is added, `view_config` is first called to determine
        that there is such a scaling group
        """
        self.group.view_config = mock.MagicMock(return_value=defer.succeed({}))
        self.returns = [[{'count': 0}], None]
        d = self.group.create_policies([{"b": "lah"}])
        self.successResultOf(d)
        self.group.view_config.assert_called_once_with()

    def test_add_scaling_policy(self):
        """
        Test that you can add a scaling policy, and what is returned is a
        list of the scaling policies with their ids
        """
        self.returns = [[{'count': 0}], None]
        d = self.group.create_policies([{"b": "lah"}])
        result = self.successResultOf(d)
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, :policy0version) '
            'APPLY BATCH;')
        expectedData = {"policy0data": '{"_ver": 1, "b": "lah"}',
                        "policy0version": 'timeuuid',
                        "groupId": '12345678g',
                        "policy0policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        self.assertEqual(result, [{'b': 'lah', 'id': self.mock_key.return_value}])

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_add_scaling_policy_at(self, mock_serial):
        """
        Test that you can add a scaling policy with 'at' schedule and what is
        returned is a list of the scaling policies with their ids
        """
        self.returns = [[{'count': 0}], None]
        expected_at = '2012-10-20T03:23:45'
        pol = {'cooldown': 5, 'type': 'schedule', 'name': 'scale up by 10', 'change': 10,
               'args': {'at': expected_at}}

        d = self.group.create_policies([pol])

        result = self.successResultOf(d)
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, :policy0version) '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, version) '
            'VALUES (:policy0bucket, :tenantId, :groupId, :policy0policyId, '
            ':policy0trigger, :policy0version) '
            'APPLY BATCH;')
        expectedData = {
            "policy0data": _S(pol),
            "groupId": '12345678g',
            "policy0policyId": '12345678',
            "policy0trigger": from_timestamp(expected_at),
            "tenantId": '11111',
            "policy0bucket": 2,
            "policy0version": 'timeuuid'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        pol['id'] = self.mock_key.return_value
        self.assertEqual(result, [pol])

    def test_add_scaling_policy_cron(self):
        """
        Test that you can add a scaling policy with 'cron' schedule and what is
        returned is a list of the scaling policies with their ids
        """
        self.returns = [[{'count': 0}], None]
        pol = {'cooldown': 5, 'type': 'schedule', 'name': 'scale up by 10', 'change': 10,
               'args': {'cron': '* * * * *'}}

        d = self.group.create_policies([pol])

        result = self.successResultOf(d)
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, :policy0version) '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, cron, version) '
            'VALUES (:policy0bucket, :tenantId, :groupId, :policy0policyId, '
            ':policy0trigger, :policy0cron, :policy0version) '
            'APPLY BATCH;')
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policy0data": ('{"name": "scale up by 10", "args": {"cron": "* * * * *"}, '
                                        '"cooldown": 5, "_ver": 1, "type": "schedule", "change": 10}'),
                        "policy0policyId": '12345678',
                        "policy0trigger": 'next_time',
                        "policy0cron": "* * * * *",
                        "policy0bucket": 2,
                        "policy0version": "timeuuid"}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        pol['id'] = self.mock_key.return_value
        self.assertEqual(result, [pol])


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

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

    def test_fetch_and_delete(self):
        """
        Tests that you can fetch and delete list of events
        """
        self.returns = [[{'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ef',
                          'trigger': 100, 'cron': 'c1', 'version': 'uuid1'},
                         {'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ex',
                          'trigger': 122, 'cron': 'c2', 'version': 'uuid2'}],
                        None]
        events = self.returns[0]

        fetch_data = {'bucket': 2, 'now': 1234, 'size': 100}
        fetch_cql = (
            'SELECT "tenantId", "groupId", "policyId", "trigger", cron, version '
            'FROM scaling_schedule_v2 '
            'WHERE bucket = :bucket AND trigger <= :now LIMIT :size;')
        del_cql = ('BEGIN BATCH '
                   'DELETE FROM scaling_schedule_v2 WHERE bucket = :bucket '
                   'AND trigger = :event0trigger AND "policyId" = :event0policyId; '
                   'DELETE FROM scaling_schedule_v2 WHERE bucket = :bucket '
                   'AND trigger = :event1trigger AND "policyId" = :event1policyId; '
                   'APPLY BATCH;')
        del_data = {'bucket': 2, 'event0trigger': 100, 'event0policyId': 'ef',
                    'event1trigger': 122, 'event1policyId': 'ex'}

        result = self.validate_fetch_and_delete(2, 1234, 100)

        self.assertEqual(result, events)
        self.assertEqual(self.connection.execute.mock_calls,
                         [mock.call(fetch_cql, fetch_data, ConsistencyLevel.QUORUM),
                          mock.call(del_cql, del_data, ConsistencyLevel.QUORUM)])

    def test_add_cron_events(self):
        """
        Tests for `add_cron_events`
        """
        self.returns = [None]
        events = [{'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ef',
                   'trigger': 100, 'cron': 'c1', 'version': 'v1'},
                  {'tenantId': '1d3', 'groupId': 'gr3', 'policyId': 'ex',
                   'trigger': 122, 'cron': 'c2', 'version': 'v2'}]
        cql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, cron, version) '
            'VALUES (:event0bucket, :event0tenantId, :event0groupId, :event0policyId, '
            ':event0trigger, :event0cron, :event0version); '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", "policyId", '
            'trigger, cron, version) '
            'VALUES (:event1bucket, :event1tenantId, :event1groupId, :event1policyId, '
            ':event1trigger, :event1cron, :event1version); '
            'APPLY BATCH;')
        data = {'event0bucket': 2, 'event0tenantId': '1d2', 'event0groupId': 'gr2',
                'event0policyId': 'ef', 'event0trigger': 100, 'event0cron': 'c1',
                'event0version': 'v1',
                'event1bucket': 3, 'event1tenantId': '1d3', 'event1groupId': 'gr3',
                'event1policyId': 'ex', 'event1trigger': 122, 'event1cron': 'c2',
                'event1version': 'v2'}
        self.collection.buckets = iter(range(2, 4))

        result = self.successResultOf(self.collection.add_cron_events(events))
        self.assertEqual(result, None)
        self.connection.execute.assert_called_once_with(
            cql, data, ConsistencyLevel.ONE)


class CassScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`CassScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock(spec=['execute'])
        set_config_data({'limits': {'absolute': {'maxGroups': 1000}}})
        self.addCleanup(set_config_data, {})

        self.returns = [[{"count": 0}], None]

        def _responses(*args):
            result = self.returns.pop(0)
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(_de_identify(result))

        self.connection.execute.side_effect = _responses

        self.mock_log = mock_log()

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

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

        # 'serializing' something just wraps it with a _S
        self.mock_serial = patch(self, 'otter.models.cass.serialize_json_data',
                                 side_effect=lambda *args: _S(args[0]))

    def test_create(self):
        """
        Test that you can create a group, and if successful the group ID is
        returned
        """
        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "policyTouched": '{}',
            "paused": False}
        expectedCql = ('BEGIN BATCH '
                       'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
                       'launch_config, active, pending, "policyTouched", '
                       'paused, created_at) '
                       'VALUES (:tenantId, :groupId, :group_config, :launch_config, :active, '
                       ':pending, :policyTouched, :paused, :created_at) '
                       'APPLY BATCH;')
        self.mock_key.return_value = '12345678'

        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch)

        self.assertEqual(result['groupConfiguration'], self.config)
        self.assertEqual(result['scalingPolicies'], [])
        self.assertEqual(result['launchConfiguration'], self.launch)
        self.assertEqual(result['id'], self.mock_key.return_value)
        self.assertTrue(isinstance(result['state'], GroupState))

        # Verify data argument seperately since data in actual call will have datetime.utcnow
        # which cannot be mocked or predicted.
        data = self.connection.execute.call_args[0][1]
        self.assertTrue(isinstance(data.pop('created_at'), datetime))
        self.assertEqual(expectedData, data)

        self.connection.execute.assert_called_with(expectedCql,
                                                   mock.ANY,
                                                   ConsistencyLevel.TWO)

    def test_create_with_policy(self):
        """
        Test that you can create a scaling group with a single policy, and if
        successful the group ID is returned
        """
        policy = group_examples.policy()[0]

        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "policyTouched": '{}',
            "paused": False,
            'policy0policyId': '12345678',
            'policy0data': _S(policy),
            'policy0version': 'timeuuid'}
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
            'launch_config, active, pending, "policyTouched", paused, created_at) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, :active, '
            ':pending, :policyTouched, :paused, :created_at) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, :policy0version) '
            'APPLY BATCH;')
        self.mock_key.return_value = '12345678'
        policy = group_examples.policy()[0]
        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch,
                                                   [policy])
        expected_policy = policy.copy()
        expected_policy['id'] = self.mock_key.return_value
        self.assertEqual(result['groupConfiguration'], self.config)
        self.assertEqual(result['scalingPolicies'], [expected_policy])
        self.assertEqual(result['launchConfiguration'], self.launch)
        self.assertEqual(result['id'], self.mock_key.return_value)
        self.assertTrue(isinstance(result['state'], GroupState))

        called_data = self.connection.execute.call_args[0][1]
        self.assertTrue(isinstance(called_data.pop('created_at'), datetime))
        self.assertEqual(called_data, expectedData)

        self.connection.execute.assert_called_with(expectedCql,
                                                   mock.ANY,
                                                   ConsistencyLevel.TWO)

    def test_create_with_policy_multiple(self):
        """
        Test that you can create a scaling group with multiple policies, and if
        successful the group ID is returned
        """
        policies = group_examples.policy()[:2]

        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '1',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "policyTouched": '{}',
            "paused": False,
            'policy0policyId': '2',
            'policy0data': _S(policies[0]),
            'policy0version': 'timeuuid',
            'policy1policyId': '3',
            'policy1data': _S(policies[1]),
            'policy1version': 'timeuuid'}
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
            'launch_config, active, pending, "policyTouched", paused, created_at) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, :active, '
            ':pending, :policyTouched, :paused, :created_at) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, :policy0version) '
            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, version) '
            'VALUES (:tenantId, :groupId, :policy1policyId, :policy1data, :policy1version) '
            'APPLY BATCH;')

        counter = [0]

        def mock_key_gen(*args, **kwargs):
            counter[0] += 1
            return str(counter[0])

        self.mock_key.side_effect = mock_key_gen
        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch,
                                                   policies)
        policies[0]['id'] = '2'
        policies[1]['id'] = '3'

        self.assertEqual(result['groupConfiguration'], self.config)
        self.assertEqual(result['scalingPolicies'], policies)
        self.assertEqual(result['launchConfiguration'], self.launch)
        self.assertEqual(result['id'], '1')
        self.assertTrue(isinstance(result['state'], GroupState))

        called_data = self.connection.execute.call_args[0][1]
        self.assertTrue(isinstance(called_data.pop('created_at'), datetime))
        self.assertEqual(called_data, expectedData)

        self.connection.execute.assert_called_with(expectedCql,
                                                   mock.ANY,
                                                   ConsistencyLevel.TWO)

    def test_max_groups_underlimit(self):
        """
        test scaling group creation when below maxGroups limit
        """
        self.returns = [[{'count': 1}], None]

        expectedData = {'tenantId': '1234'}
        expectedCQL = 'SELECT COUNT(*) FROM scaling_group WHERE "tenantId" = :tenantId;'

        d = self.collection.create_scaling_group(mock.Mock(), '1234', self.config, self.launch)
        self.assertTrue(isinstance(self.successResultOf(d), dict))

        self.assertEqual(len(self.connection.execute.mock_calls), 2)
        self.assertEqual(self.connection.execute.mock_calls[0],
                         mock.call(expectedCQL, expectedData, ConsistencyLevel.TWO))

    def test_max_groups_overlimit(self):
        """
        test scaling group creation when at maxGroups limit
        """
        set_config_data({'limits': {'absolute': {'maxGroups': 1}}})
        self.returns = [[{'count': 1}]]

        expectedData = {'tenantId': '1234'}
        expectedCQL = 'SELECT COUNT(*) FROM scaling_group WHERE "tenantId" = :tenantId;'

        d = self.collection.create_scaling_group(mock.Mock(), '1234', self.config, self.launch)
        self.connection.execute.assert_called_once_with(expectedCQL,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

        self.failureResultOf(d, ScalingGroupOverLimitError)

    def test_list_states(self):
        """
        ``list_scaling_group_states`` returns a list of :class:`GroupState`
        objects from cassandra
        """
        self.returns = [[{
            'tenantId': '123',
            'groupId': 'group{}'.format(i),
            'group_config': '{"name": "test"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00',
            'created_at': 23
        } for i in range(2)]]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM '
                       'scaling_group WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, [
            GroupState('123', 'group0', 'test', {}, {}, '0001-01-01T00:00:00Z', {}, False),
            GroupState('123', 'group1', 'test', {}, {}, '0001-01-01T00:00:00Z', {}, False)])

    def test_list_empty(self):
        """
        If there are no states in cassandra, ``list_scaling_group_states``
        returns an empty list
        """
        self.returns = [[]]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM '
                       'scaling_group WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(r, [])
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_states_respects_limit(self):
        """
        If there are more than the requested number of states,
        ``list_scaling_group_states`` only requests the requested number.
        """
        self.returns = [[]]
        expectedData = {'tenantId': '123', 'limit': 5}
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM '
                       'scaling_group WHERE "tenantId" = :tenantId LIMIT :limit;')
        self.collection.list_scaling_group_states(self.mock_log, '123', limit=5)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_states_offsets_by_marker(self):
        """
        If a marker is provided, it is passed into the CQL as a where clause
        """
        self.returns = [[]]
        expectedData = {'tenantId': '123', 'limit': 100, 'marker': '345'}
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM '
                       'scaling_group WHERE "tenantId" = :tenantId AND '
                       '"groupId" > :marker LIMIT :limit;')
        self.collection.list_scaling_group_states(self.mock_log, '123',
                                                  marker='345')
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_states_does_not_return_resurrected_groups(self):
        """
        If any of the rows returned is resurrected, i.e. does not contain created_at
        then it is not returned
        """
        group_dicts = [{
            'tenantId': '123',
            'groupId': 'group123',
            'group_config': '{"name": "test123"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00',
            'created_at': 23
        }, {
            'tenantId': '23',
            'groupId': 'group23',
            'group_config': '{"name": "test123"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00',
            'created_at': None
        }]
        self.returns = [group_dicts, None]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = ('SELECT "tenantId", "groupId", group_config, active, pending, '
                       '"groupTouched", "policyTouched", paused, created_at FROM '
                       'scaling_group WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(self.connection.execute.call_args_list[0],
                         mock.call(expectedCql, expectedData, ConsistencyLevel.TWO))
        self.assertEqual(r, [
            GroupState('123', 'group123', 'test123', {}, {}, '0001-01-01T00:00:00Z', {}, False)])
        self.mock_log.msg.assert_called_once_with('Resurrected rows', tenant_id='123',
                                                  rows=[_de_identify(group_dicts[1])])

    def test_list_states_deletes_resurrected_groups(self):
        """
        If any of the rows returned is resurrected, i.e. does not contain created_at
        then it is triggered for deletion
        """
        group_dicts = [{
            'tenantId': '123',
            'groupId': 'group123',
            'group_config': '{"name": "test123"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00',
            'created_at': 23
        }, {
            'tenantId': '23',
            'groupId': 'group23',
            'group_config': '{"name": "test123"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': '\x00',
            'created_at': None
        }]
        self.returns = [group_dicts, None]

        expectedCql = 'DELETE FROM scaling_group WHERE "groupId" IN (:column_value0);'
        expectedData = {'column_value0': 'group23'}
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(self.connection.execute.call_count, 2)
        self.assertEqual(self.connection.execute.call_args_list[1],
                         mock.call(expectedCql, expectedData, ConsistencyLevel.TWO))
        self.assertEqual(r, [
            GroupState('123', 'group123', 'test123', {}, {}, '0001-01-01T00:00:00Z', {}, False)])

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
        self.failureResultOf(d, UnrecognizedCapabilityError)
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
        config_query = ('SELECT COUNT(*) FROM scaling_group WHERE "tenantId" = :tenantId;')
        policy_query = ('SELECT COUNT(*) FROM scaling_policies WHERE "tenantId" = :tenantId;')
        webhook_query = ('SELECT COUNT(*) FROM policy_webhooks WHERE "tenantId" = :tenantId;')

        calls = [mock.call(config_query, expectedData, ConsistencyLevel.TWO),
                 mock.call(policy_query, expectedData, ConsistencyLevel.TWO),
                 mock.call(webhook_query, expectedData, ConsistencyLevel.TWO)]

        d = self.collection.get_counts(self.mock_log, '123')
        result = self.successResultOf(d)
        self.assertEquals(result, expectedResults)
        self.connection.execute.assert_has_calls(calls)


class CassScalingGroupsCollectionHealthCheckTestCase(
        IScalingGroupCollectionProviderMixin, TestCase):
    """
    Tests for :class:`CassScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock(spec=['execute'])
        self.connection.execute.return_value = defer.succeed([])
        self.collection = CassScalingGroupCollection(self.connection)
        self.collection.kz_client = mock.MagicMock(connected=True,
                                                   state=KazooState.CONNECTED)
        self.clock = Clock()

    def test_health_check_no_zookeeper(self):
        """
        Health check fails if there is no zookeeper client
        """
        self.collection.kz_client = None
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (False, matches(ContainsDict(
                {'zookeeper': Equals(False),
                 'zookeeper_state': Equals('Not connected yet')}))))

    def test_health_check_zookeeper_not_connected(self):
        """
        Health check fails if there is no zookeeper client
        """
        self.collection.kz_client = mock.MagicMock(connected=False)
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (False, matches(ContainsDict(
                {'zookeeper': Equals(False),
                 'zookeeper_state': Equals('Not connected yet')}))))

    def test_health_check_zookeeper_connected(self):
        """
        Health check for zookeeper succeeds if the zookeeper client state is
        CONNECTED
        """
        self.collection.kz_client = mock.MagicMock(connected=True,
                                                   state=KazooState.CONNECTED)
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (True, matches(ContainsDict(
                {'zookeeper': Equals(True),
                 'zookeeper_state': Equals('CONNECTED')}))))

    def test_health_check_zookeeper_suspended(self):
        """
        Health check fails if the zookeeper client state is not CONNECTED
        """
        self.collection.kz_client = mock.MagicMock(connected=True,
                                                   state=KazooState.SUSPENDED)
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (False, matches(ContainsDict(
                {'zookeeper': Equals(False),
                 'zookeeper_state': Equals('SUSPENDED')}))))

    def test_health_check_cassandra_fails(self):
        """
        Health check fails if cassandra fails
        """
        self.connection.execute.return_value = defer.fail(Exception('boo'))
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (False, matches(ContainsDict(
                {'cassandra': Equals(False),
                 'cassandra_failure': Equals("Exception('boo',)"),
                 'cassandra_time': Equals(0)}))))

    def test_health_check_cassandra_times_out(self):
        """
        Health check for cassandra fails if cassandra check times out
        """
        self.connection.execute.return_value = defer.Deferred()
        d = self.collection.health_check(self.clock)
        self.assertNoResult(d)

        self.clock.advance(15)
        self.assertEqual(
            self.successResultOf(d),
            (False, matches(ContainsDict(
                {'cassandra': Equals(False),
                 'cassandra_failure': Equals("TimedOutError('cassandra health check "
                                             "timed out after 15 seconds.',)"),
                 'cassandra_time': Equals(15)}))))
        # to make sure the deferred doesn't get GCed without being called
        self.connection.execute.return_value.callback(None)

    def test_health_check_cassandra_succeeds(self):
        """
        Health check fails if cassandra fails
        """
        d = self.collection.health_check(self.clock)
        self.assertEqual(
            self.successResultOf(d),
            (True, matches(ContainsDict(
                {'cassandra': Equals(True),
                 'cassandra_time': Equals(0)}))))

    def test_health_check_succeeds_if_both_succeed(self):
        """
        If both zookeeper and cassandra are healthy, the store is healthy
        """
        d = self.collection.health_check(self.clock)
        self.assertEqual(self.successResultOf(d), (True, mock.ANY))


class CassAdminTestCase(TestCase):
    """
    Tests for :class:`CassAdmin`
    """

    def setUp(self):
        """ Setup mocks """
        self.connection = mock.MagicMock(spec=['execute'])

        self.returns = [None]

        def _responses(*args):
            result = _de_identify(self.returns.pop(0))
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.mock_log = mock.MagicMock()

        self.collection = CassAdmin(self.connection)

        patch(self, 'otter.models.cass.get_consistency_level',
              return_value=ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.time')
    def test_get_metrics(self, time):
        """
        Check get_metrics returns dictionary in proper format
        """
        time.time.return_value = 1234567890

        self.returns = [
            [{'count': 190}],
            [{'count': 191}],
            [{'count': 192}],
        ]

        # These are now reversed for an unknown reason.
        expectedResults = [
            {
                'id': 'otter.metrics.groups',
                'value': 190,
                'time': 1234567890
            },
            {
                'id': 'otter.metrics.policies',
                'value': 191,
                'time': 1234567890
            },
            {
                'id': 'otter.metrics.webhooks',
                'value': 192,
                'time': 1234567890
            }
        ]
        config_query = ('SELECT COUNT(*) FROM scaling_group;')
        policy_query = ('SELECT COUNT(*) FROM scaling_policies;')
        webhook_query = ('SELECT COUNT(*) FROM policy_webhooks;')

        calls = [mock.call(config_query, {}, ConsistencyLevel.TWO),
                 mock.call(policy_query, {}, ConsistencyLevel.TWO),
                 mock.call(webhook_query, {},  ConsistencyLevel.TWO)]

        d = self.collection.get_metrics(self.mock_log)
        result = self.successResultOf(d)
        self.assertEquals(result, expectedResults)
        self.connection.execute.assert_has_calls(calls)
