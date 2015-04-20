"""
Tests for :mod:`otter.models.cass`
"""
import itertools
import json
from collections import namedtuple
from copy import deepcopy
from datetime import datetime
from functools import partial

from effect import Effect, ParallelEffects, TypeDispatcher, sync_perform
from effect.testing import SequenceDispatcher, resolve_effect
from effect.twisted import deferred_performer

from jsonschema import ValidationError

from kazoo.exceptions import NotEmptyError
from kazoo.protocol.states import KazooState

import mock

from pyrsistent import freeze

from silverberg.client import CQLClient, ConsistencyLevel

from testtools.matchers import IsInstance

from toolz.dicttoolz import assoc

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.effect_dispatcher import get_simple_dispatcher
from otter.json_schema import group_examples
from otter.models.cass import (
    CQLQueryExecute,
    CassAdmin,
    CassScalingGroup,
    CassScalingGroupCollection,
    WeakLocks,
    _assemble_webhook_from_row,
    assemble_webhooks_in_policies,
    get_cql_dispatcher,
    perform_cql_query,
    serialize_json_data,
    verified_view,
    webhook_by_hash_effect
)
from otter.models.interface import (
    GroupNotEmptyError,
    GroupState,
    NoSuchPolicyError,
    NoSuchScalingGroupError,
    NoSuchWebhookError,
    PoliciesOverLimitError,
    ScalingGroupOverLimitError,
    ScalingGroupStatus,
    UnrecognizedCapabilityError,
    WebhooksOverLimitError
)
from otter.test.models.test_interface import (
    IScalingGroupCollectionProviderMixin,
    IScalingGroupProviderMixin,
    IScalingScheduleCollectionProviderMixin
)
from otter.test.test_effect_dispatcher import simple_intents
from otter.test.utils import (
    DummyException,
    LockMixin,
    matches,
    mock_log,
    patch,
    raise_)
from otter.util.config import set_config_data
from otter.util.timestamp import from_timestamp


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
    return from a list of dictionaries.  So for instance, passing the
    following:

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


class PerformTests(SynchronousTestCase):
    """
    Tests for :func:`perform_cql_query` function
    """

    def test_perform_cql_query(self):
        """
        Calls given connection's execute
        """
        conn = mock.Mock(spec=CQLClient)
        conn.execute.return_value = defer.succeed('ret')
        intent = CQLQueryExecute(query='query', params={'w': 2},
                                 consistency_level=ConsistencyLevel.ONE)
        r = sync_perform(
            TypeDispatcher({CQLQueryExecute: partial(perform_cql_query,
                                                     conn)}),
            Effect(intent))
        self.assertEqual(r, 'ret')
        conn.execute.assert_called_once_with(
            'query', {'w': 2}, ConsistencyLevel.ONE)


class CQLDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_cql_dispatcher`."""

    def test_intent_support(self):
        """Basic intents are supported by the dispatcher."""
        dispatcher = get_simple_dispatcher(None)
        for intent in simple_intents():
            self.assertIsNot(dispatcher(intent), None)

    @mock.patch('otter.models.cass.perform_cql_query')
    def test_cql_disp(self, mock_pcq):
        """The :obj:`CQLQueryExecute` performer is called."""

        @deferred_performer
        def performer(c, d, i):
            return defer.succeed('p' + c)

        mock_pcq.side_effect = performer

        dispatcher = get_cql_dispatcher(object(), 'conn')
        intent = CQLQueryExecute(query='q', params='p', consistency_level=1)
        eff = Effect(intent)
        self.assertEqual(sync_perform(dispatcher, eff), 'pconn')


class SerialJsonDataTestCase(SynchronousTestCase):
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


class AssembleWebhooksTests(SynchronousTestCase):
    """
    Tests for `assemble_webhooks_in_policies`
    """

    def setUp(self):
        """
        sample policies, mock _assemble_webhook_from_row
        """
        self.policies = [{'id': str(i)} for i in range(10)]
        self.awfr = patch(self, 'otter.models.cass._assemble_webhook_from_row')
        self.awfr.side_effect = lambda w, **ka: w['policyId'] + w['webhookId']

    def test_no_webhooks(self):
        """
        No webhooks in any policies
        """
        policies = assemble_webhooks_in_policies(self.policies, [])
        for policy in policies:
            self.assertEqual(policy['webhooks'], [])

    def test_no_policies(self):
        """
        No policies will just return same empty list
        """
        self.assertEqual(assemble_webhooks_in_policies([], []), [])
        self.assertEqual(
            assemble_webhooks_in_policies(
                [], [{'policyId': '1', 'webhookId': 'w'}]),
            [])

    def test_all_webhooks(self):
        """
        All the policies have webhooks
        """
        webhooks = [{'policyId': str(i), 'webhookId': 'p{}{}'.format(i, j)}
                    for i in range(len(self.policies)) for j in [0, 1]]
        policies = assemble_webhooks_in_policies(self.policies, webhooks)
        for i, policy in enumerate(policies):
            self.assertEqual(policy['webhooks'],
                             ['{}p{}0'.format(i, i), '{}p{}1'.format(i, i)])

    def test_some_webhooks(self):
        """
        Only some policies have webhooks
        """
        webhooks = [{'policyId': '0', 'webhookId': 'w01'},
                    {'policyId': '0', 'webhookId': 'w02'},
                    {'policyId': '1', 'webhookId': 'w11'},
                    {'policyId': '3', 'webhookId': 'w31'},
                    {'policyId': '3', 'webhookId': 'w32'},
                    {'policyId': '9', 'webhookId': 'w91'}]
        policies = assemble_webhooks_in_policies(self.policies, webhooks)
        for i in set(range(10)) - set([0, 1, 3, 9]):
            self.assertEqual(policies[i]['webhooks'], [])
        self.assertEqual(policies[0]['webhooks'], ['0w01', '0w02'])
        self.assertEqual(policies[1]['webhooks'], ['1w11'])
        self.assertEqual(policies[3]['webhooks'], ['3w31', '3w32'])
        self.assertEqual(policies[9]['webhooks'], ['9w91'])

    def test_last_policies(self):
        """
        Last policies with no webhooks have empty list
        """
        webhooks = [{'policyId': '0', 'webhookId': 'w01'},
                    {'policyId': '0', 'webhookId': 'w02'},
                    {'policyId': '1', 'webhookId': 'w11'}]
        policies = assemble_webhooks_in_policies(self.policies, webhooks)
        for i in range(2, 10):
            self.assertEqual(policies[i]['webhooks'], [])
        self.assertEqual(policies[0]['webhooks'], ['0w01', '0w02'])
        self.assertEqual(policies[1]['webhooks'], ['1w11'])

    def test_extra_webhooks(self):
        """
        webhooks that don't belong to any policy is ignored
        """
        webhooks = [{'policyId': '0', 'webhookId': 'w01'},
                    {'policyId': '15', 'webhookId': 'w151'},
                    {'policyId': '3', 'webhookId': 'w31'},
                    {'policyId': '35', 'webhookId': 'w351'},
                    {'policyId': '9', 'webhookId': 'w91'}]
        policies = assemble_webhooks_in_policies(self.policies, webhooks)
        for i in set(range(10)) - set([0, 3, 9]):
            self.assertEqual(policies[i]['webhooks'], [])
        self.assertEqual(policies[0]['webhooks'], ['0w01'])
        self.assertEqual(policies[3]['webhooks'], ['3w31'])
        self.assertEqual(policies[9]['webhooks'], ['9w91'])


class VerifiedViewTests(SynchronousTestCase):
    """
    Tests for `verified_view`.
    """

    def setUp(self):
        """
        Mock connection object.
        """
        self.connection = mock.Mock(spec=CQLClient)
        self.log = mock_log()

    def _verified_view(self, get_deleting=False):
        """
        Returns a verified view, with some test arguments.
        """
        return verified_view(
            self.connection, 'vq', 'dq', {'d': 2}, ConsistencyLevel.TWO,
            ValueError, self.log, get_deleting=get_deleting)

    def test_valid_view(self):
        """
        Returns row if it is valid
        """
        self.connection.execute.return_value = defer.succeed(
            [{'c1': 2, 'created_at': 23}])
        r = self._verified_view()
        self.assertEqual(self.successResultOf(r), {'c1': 2, 'created_at': 23})
        self.connection.execute.assert_called_once_with(
            'vq', {'d': 2}, ConsistencyLevel.TWO)
        self.assertFalse(self.log.msg.called)

    def test_get_deleting_group(self):
        """
        Get DELETING group when get_deleting=True
        """
        self.connection.execute.return_value = defer.succeed(
            [{'c1': 2, 'created_at': 23, 'deleting': True}])
        r = self._verified_view(get_deleting=True)
        self.assertEqual(
            self.successResultOf(r),
            {'c1': 2, 'created_at': 23, 'deleting': True})
        self.connection.execute.assert_called_once_with(
            'vq', {'d': 2}, ConsistencyLevel.TWO)
        self.assertFalse(self.log.msg.called)

    def test_false_get_deleting_group(self):
        """
        Raises empty exception when get_deleting=False and group is deleting
        """
        self.connection.execute.return_value = defer.succeed(
            [{'c1': 2, 'created_at': 23, 'deleting': True}])
        r = self._verified_view(get_deleting=False)
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_called_once_with(
            'vq', {'d': 2}, ConsistencyLevel.TWO)
        self.assertFalse(self.log.msg.called)

    def test_resurrected_view(self):
        """
        Raise empty error if resurrected view
        """
        self.connection.execute.return_value = defer.succeed(
            [{'c1': 2, 'created_at': None}])
        r = self._verified_view()
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_has_calls(
            [mock.call('vq', {'d': 2}, ConsistencyLevel.TWO),
             mock.call('dq', {'d': 2}, ConsistencyLevel.TWO)])
        self.log.msg.assert_called_once_with(
            'Resurrected row',
            row={'c1': 2, 'created_at': None},
            row_params={'d': 2})

    def test_del_does_not_wait(self):
        """
        When a resurrected row is encountered it is triggered for deletion
        and `verified_view` does not wait for its result before
        returning.
        """
        first_time = [True]

        def _execute(*args):
            if first_time[0]:
                first_time[0] = False
                return defer.succeed([{'c1': 2, 'created_at': None}])
            return defer.Deferred()

        self.connection.execute.side_effect = _execute
        r = self._verified_view()
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_has_calls(
            [mock.call('vq', {'d': 2}, ConsistencyLevel.TWO),
             mock.call('dq', {'d': 2}, ConsistencyLevel.TWO)])

    def test_empty_view(self):
        """
        Raise empty error if no result
        """
        self.connection.execute.return_value = defer.succeed([])
        r = self._verified_view()
        self.failureResultOf(r, ValueError)
        self.connection.execute.assert_called_once_with(
            'vq', {'d': 2}, ConsistencyLevel.TWO)
        self.assertFalse(self.log.msg.called)


class WeakLocksTests(SynchronousTestCase):
    """
    Tests for `WeakLocks`
    """

    def setUp(self):
        """
        Sample `WeakLocks` object
        """
        self.locks = WeakLocks()

    def test_returns_deferlock(self):
        """
        `get_lock` returns a `DeferredLock`
        """
        self.assertIsInstance(self.locks.get_lock('a'), defer.DeferredLock)

    def test_same_lock(self):
        """
        `get_lock` on same uuid returns same `DeferredLock`
        """
        self.assertIs(self.locks.get_lock('a'), self.locks.get_lock('a'))

    def test_diff_lock(self):
        """
        `get_lock` on different uuid returns different `DeferredLock`
        """
        self.assertIsNot(self.locks.get_lock('a'), self.locks.get_lock('b'))


class CassScalingGroupTestCase(IScalingGroupProviderMixin, LockMixin,
                               SynchronousTestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.connection = mock.MagicMock(spec=CQLClient)
        set_config_data({'limits':
                         {'absolute': {'maxWebhooksPerPolicy': 1000}}})
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
        launch_config = group_examples.launch_server_config()[0]
        self.launch_config = _de_identify(launch_config)
        self.policies = []
        self.mock_log = mock.MagicMock()

        self.kz_client = mock.Mock()
        self.lock = self.mock_lock()
        self.kz_client.Lock.return_value = self.lock
        self.kz_client.delete.return_value = defer.succeed('something else')

        self.clock = Clock()
        locks = WeakLocks()

        self.group = CassScalingGroup(self.mock_log,
                                      self.tenant_id,
                                      self.group_id,
                                      self.connection,
                                      itertools.cycle(range(2, 10)),
                                      self.kz_client,
                                      self.clock,
                                      locks)
        self.assertIs(self.group.local_locks, locks)
        self.mock_log.bind.assert_called_once_with(
            system='CassScalingGroup',
            tenant_id=self.tenant_id,
            scaling_group_id=self.group_id)
        self.mock_log = self.mock_log.bind()

        self.mock_key = patch(self, 'otter.models.cass.generate_key_str',
                              return_value='12345678')
        self.mock_capability = patch(
            self, 'otter.models.cass.generate_capability',
            return_value=('ver', 'hash'))

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

        self.mock_next_cron_occurrence = patch(
            self, 'otter.models.cass.next_cron_occurrence',
            return_value='next_time')


class CassScalingGroupTests(CassScalingGroupTestCase):
    """
    CassScalingGroup's tests.
    """

    def test_with_timestamp(self):
        """
        `with_timestamp` calls the decorated function with the timestamp
        got from `get_client_ts`.
        """
        self.clock.advance(23.566783)

        @self.group.with_timestamp
        def f(ts, a, b):
            "f"
            self.ts = ts
            self.a = a
            self.b = b
            return 45

        d = f(2, 3)
        # Wrapped function's return is same
        self.assertEqual(self.successResultOf(d), 45)
        # Timestamp and arguments are passed correctly
        self.assertEqual(self.ts, 23566783)
        self.assertEqual(self.a, 2)
        self.assertEqual(self.b, 3)
        # has same docstring
        self.assertEqual(f.__doc__, 'f')

    def test_view_config(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [[{'group_config': '{}', 'created_at': 24}]]
        d = self.group.view_config()
        r = self.successResultOf(d)
        expectedCql = ('SELECT group_config, created_at, deleting '
                       'FROM scaling_group '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)
        self.assertEqual(r, {})

    def test_view_config_recurrected_entry(self):
        """
        If group row returned is resurrected, i.e. does not have
        'created_at', then NoSuchScalingGroupError is returned and
        that row's deletion is triggered.
        """
        self.returns = [[{'group_config': '{}', 'created_at': None}], None]
        r = self.group.view_config()
        self.failureResultOf(r, NoSuchScalingGroupError)
        view_cql = ('SELECT group_config, created_at, deleting '
                    'FROM scaling_group '
                    'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        del_cql = ('DELETE FROM scaling_group WHERE '
                   '"tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_has_calls(
            [mock.call(view_cql, expectedData, ConsistencyLevel.QUORUM),
             mock.call(del_cql, expectedData, ConsistencyLevel.QUORUM)])

    def test_view_state(self):
        """
        Test that you can call view state and receive a valid parsed response
        """
        cass_response = [
            {'tenantId': self.tenant_id,
             'groupId': self.group_id,
             'group_config': '{"name": "a"}',
             'active': '{"A":"R"}',
             'pending': '{"P":"R"}',
             'groupTouched': '2014-01-01T00:00:05Z.1234',
             'policyTouched': '{"PT":"R"}',
             'paused': False,
             'created_at': 23,
             'desired': 10}]
        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        group_state = GroupState(tenant_id=self.tenant_id,
                                 group_id=self.group_id,
                                 group_name='a',
                                 active={'A': 'R'},
                                 pending={'P': 'R'},
                                 group_touched='2014-01-01T00:00:05Z.1234',
                                 policy_touched={'PT': 'R'},
                                 paused=False,
                                 desired=10)
        self.assertEqual(r, group_state)

    def test_view_state_no_desired_capacity(self):
        """
        If there is no desired capacity, it defaults to 0
        """
        cass_response = [
            {'tenantId': self.tenant_id,
             'groupId': self.group_id,
             'group_config': '{"name": "a"}',
             'active': '{"A":"R"}',
             'pending': '{"P":"R"}',
             'groupTouched': '2014-01-01T00:00:05Z.1234',
             'policyTouched': '{"PT":"R"}',
             'paused': False,
             'created_at': 23,
             'desired': None}]
        self.returns = [cass_response]
        r = self.successResultOf(self.group.view_state())
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'},
                                       {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       False,
                                       desired=0))

    def test_view_respsects_consistency_argument(self):
        """
        If a consistency argument is passed to ``view_state``, it is honored
        over the default consistency
        """
        cass_response = [
            {'tenantId': self.tenant_id,
             'groupId': self.group_id,
             'group_config': '{"name": "a"}',
             'active': '{"A":"R"}',
             'pending': '{"P":"R"}',
             'groupTouched': '2014-01-01T00:00:05Z.1234',
             'policyTouched': '{"PT":"R"}',
             'paused': False,
             'desired': 0,
             'created_at': 23}]
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
        If group row returned is resurrected, i.e. does not have
        'created_at', then NoSuchScalingGroupError is returned and
        that row's deletion is triggered.
        """
        cass_response = [
            {'tenantId': self.tenant_id,
             'groupId': self.group_id,
             'group_config': '{"name": "a"}',
             'active': '{"A":"R"}',
             'pending': '{"P":"R"}',
             'groupTouched': '2014-01-01T00:00:05Z.1234',
             'policyTouched': '{"PT":"R"}',
             'paused': False,
             'desired': None,
             'created_at': None}]
        self.returns = [cass_response, None]
        d = self.group.view_state()
        self.failureResultOf(d, NoSuchScalingGroupError)
        viewCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        delCql = ('DELETE FROM scaling_group '
                  'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.connection.execute.assert_has_calls(
            [mock.call(viewCql, expectedData, ConsistencyLevel.QUORUM),
             mock.call(delCql, expectedData, ConsistencyLevel.QUORUM)])

    def test_view_paused_state(self):
        """
        view_state returns a dictionary with a key paused equal to True for a
        paused group.
        """
        cass_response = _cassandrify_data([
            {'tenantId': self.tenant_id,
             'groupId': self.group_id,
             'group_config': '{"name": "a"}',
             'active': '{"A":"R"}',
             'pending': '{"P":"R"}',
             'groupTouched': '2014-01-01T00:00:05Z.1234',
             'policyTouched': '{"PT":"R"}',
             'paused': True,
             'desired': 0,
             'created_at': 3}])

        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.successResultOf(d)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'}, {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       True,
                                       desired=0))

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
        modifier.assert_called_once_with(
            self.group, 'state', 'arg1', kwarg1='1')

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

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_succeeds(self, mock_serial):
        """
        ``modify_state`` writes the state the modifier returns to the database
        with default quorum consistency for everything
        """
        def modifier(_group, _state):
            group_state = GroupState(tenant_id=self.tenant_id,
                                     group_id=self.group_id,
                                     group_name='a',
                                     active={},
                                     pending={},
                                     group_touched=None,
                                     policy_touched={},
                                     paused=True,
                                     desired=5)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        self.clock.advance(10.345)

        d = self.group.modify_state(modifier)
        self.assertEqual(self.successResultOf(d), None)
        self.group.view_state.assert_called_once_with(ConsistencyLevel.QUORUM)
        expectedCql = (
            'INSERT INTO scaling_group("tenantId", "groupId", active, '
            'pending, "groupTouched", "policyTouched", paused, desired) '
            'VALUES(:tenantId, :groupId, :active, :pending, :groupTouched, '
            ':policyTouched, :paused, :desired) USING TIMESTAMP :ts')
        expectedData = {"tenantId": self.tenant_id, "groupId": self.group_id,
                        "active": _S({}), "pending": _S({}),
                        "groupTouched": '0001-01-01T00:00:00Z',
                        "policyTouched": _S({}),
                        "paused": True, "desired": 5, "ts": 10345000}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        self.kz_client.Lock.assert_called_once_with(
            '/locks/' + self.group.uuid)

        self.lock._acquire.assert_called_once_with(timeout=120)
        self.lock.release.assert_called_once_with()

    def test_modify_state_local_lock_before_kz_lock(self):
        """
        ``modify_state`` first acquires local lock then acquires kz lock
        """
        def modifier(_group, _state):
            group_state = GroupState(tenant_id=self.tenant_id,
                                     group_id=self.group_id,
                                     group_name='a',
                                     active={},
                                     pending={},
                                     group_touched=None,
                                     policy_touched={},
                                     paused=True,
                                     desired=5)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        # setup local lock
        llock = defer.DeferredLock()
        self.group.local_locks = mock.Mock(
            get_lock=mock.Mock(return_value=llock))

        # setup local and kz lock acquire and release returns
        local_acquire_d = defer.Deferred()
        llock.acquire = mock.Mock(return_value=local_acquire_d)
        llock.release = mock.Mock(return_value=defer.succeed(None))
        release_d = defer.Deferred()
        self.lock.release.side_effect = lambda: release_d

        d = self.group.modify_state(modifier)

        self.assertNoResult(d)
        # local lock was tried, but kz lock was not
        llock.acquire.assert_called_once_with()
        self.assertFalse(self.lock._acquire.called)
        # After local lock acquired, kz lock is acquired
        local_acquire_d.callback(None)
        self.lock._acquire.assert_called_once_with(timeout=120)
        # first kz lock is released
        self.lock.release.assert_called_once_with()
        self.assertFalse(llock.release.called)
        # then local lock is relased
        release_d.callback(None)
        llock.release.assert_called_once_with()

        self.assertEqual(self.successResultOf(d), None)

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_lock_not_acquired(self, mock_serial):
        """
        ``modify_state`` raises error if lock is not acquired and does not
        do anything else
        """
        self.lock.acquire.side_effect = \
            lambda timeout: defer.fail(ValueError('a'))

        def modifier(group, state):
            raise

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.failureResultOf(d, ValueError)

        self.assertEqual(self.connection.execute.call_count, 0)
        self.kz_client.Lock.assert_called_once_with(
            '/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        self.assertEqual(self.lock.release.call_count, 0)

    def test_modify_state_lock_log_category_locking(self):
        """
        `modify_state` locking logs with category='locking'
        """
        def modifier(_group, _state):
            group_state = GroupState(tenant_id=self.tenant_id,
                                     group_id=self.group_id,
                                     group_name='a',
                                     active={},
                                     pending={},
                                     group_touched=None,
                                     policy_touched={},
                                     paused=True)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        self.returns = [None, None]
        log = self.group.log = mock.Mock()

        self.group.modify_state(modifier)

        log.bind.assert_called_once_with(
            system='CassScalingGroup.modify_state')
        log.bind().bind.assert_called_once_with(category='locking')
        self.assertEqual(log.bind().bind().msg.call_count, 4)

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
        def modifier(_group, _state):
            group_state = GroupState(tenant_id='tid',
                                     group_id=self.group_id,
                                     group_name='a',
                                     active={},
                                     pending={},
                                     group_touched=None,
                                     policy_touched={},
                                     paused=True)
            return group_state

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
        def modifier(_group, _state):
            group_state = GroupState(tenant_id=self.tenant_id,
                                     group_id='gid',
                                     group_name='name',
                                     active={},
                                     pending={},
                                     group_touched=None,
                                     policy_touched={},
                                     paused=True)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        f = self.failureResultOf(d)
        self.assertTrue(f.check(AssertionError))
        self.assertEqual(self.connection.execute.call_count, 0)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_status(self, mock_vc):
        """
        ``update_status`` updates the status column with given named constant
        """
        self.clock.advance(10.345)
        d = self.group.update_status(ScalingGroupStatus.ERROR)
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'INSERT INTO scaling_group("tenantId", "groupId", status) '
            'VALUES (:tenantId, :groupId, :status) USING TIMESTAMP :ts')
        expectedData = {"status": 'ERROR',
                        "groupId": '12345678g',
                        "tenantId": '11111', 'ts': 10345000}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    def test_update_status_raises_nogroup_error(self, mock_vc):
        """
        ``update_status`` raises ``NoSuchScalingGroupError`` if group in
        the object does not exist.
        """
        self.clock.advance(10.345)
        d = self.group.update_status(ScalingGroupStatus.ACTIVE)
        self.failureResultOf(d, NoSuchScalingGroupError)
        self.assertFalse(self.connection.execute.called)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_status_deleting(self, mock_vc):
        """
        Sets "deleting" column to true when status set is DELETING
        """
        self.clock.advance(10.345)
        d = self.group.update_status(ScalingGroupStatus.DELETING)
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'INSERT INTO scaling_group("tenantId", "groupId", deleting) '
            'VALUES (:tenantId, :groupId, :deleting) USING TIMESTAMP :ts')
        expectedData = {"deleting": True,
                        "groupId": '12345678g',
                        "tenantId": '11111', 'ts': 10345000}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    def test_view_config_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_config()
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = (
            'SELECT group_config, created_at, deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        expectedCql = (
            'SELECT launch_config, created_at, deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        self.assertEqual(r, {})

    def test_view_launch_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = (
            'SELECT launch_config, created_at, deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        When viewing the launch config, if the returned row is resurrected
        row, it is not returned and it is triggerred for deletion.
        """
        mock_verfied_view.return_value = defer.fail(
            NoSuchScalingGroupError('a', 'b'))
        d = self.group.view_launch_config()
        self.failureResultOf(d, NoSuchScalingGroupError)
        viewCql = ('SELECT launch_config, created_at, deleting '
                   'FROM scaling_group WHERE '
                   '"tenantId" = :tenantId AND "groupId" = :groupId;')
        delCql = ('DELETE FROM scaling_group WHERE '
                  '"tenantId" = :tenantId AND "groupId" = :groupId')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        mock_verfied_view.assert_called_once_with(
            self.connection, viewCql, delCql, expectedData,
            ConsistencyLevel.QUORUM,
            matches(IsInstance(NoSuchScalingGroupError)),
            self.mock_log)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_config(self, view_config):
        """
        Test that you can update a config, and if its successful the return
        value is None
        """
        self.clock.advance(10.345)
        d = self.group.update_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_group("tenantId", "groupId", group_config) '
            'VALUES (:tenantId, :groupId, :scaling) USING TIMESTAMP :ts '
            'APPLY BATCH;')
        expectedData = {"scaling": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111', 'ts': 10345000}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_launch(self, view_config):
        """
        Test that you can update a launch config, and if successful the return
        value is None
        """
        self.clock.advance(10.345)
        d = self.group.update_launch_config({"b": "lah"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH '
            'INSERT INTO scaling_group("tenantId", "groupId", launch_config) '
            'VALUES (:tenantId, :groupId, :launch) USING TIMESTAMP :ts '
            'APPLY BATCH;')
        expectedData = {"launch": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "tenantId": '11111', 'ts': 10345000}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        expectedCql = (
            'SELECT data, version FROM scaling_policies '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId '
            'AND "policyId" = :policyId;')
        expectedData = {"tenantId": "11111",
                        "groupId": "12345678g",
                        "policyId": "3444"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        self.assertEqual(r, {})

    def test_view_policy_no_such_policy(self):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.get_policy('3444')
        self.failureResultOf(d, NoSuchPolicyError)
        expectedCql = (
            'SELECT data, version '
            'FROM scaling_policies '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId '
            'AND "policyId" = :policyId;')
        expectedData = {"tenantId": "11111",
                        "groupId": "12345678g",
                        "policyId": "3444"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId;')
        d = self.group._naive_list_policies()
        r = self.successResultOf(d)
        self.assertEqual(r, [{'id': 'policy1'}, {'id': 'policy2'}])

        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks',
                return_value=defer.succeed([{'webhookKey': 'w1'},
                                            {'webhookKey': 'w2'}]))
    def test_delete_policy_valid_policy(self, mock_webhooks, mock_get_policy):
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
            'DELETE FROM webhook_keys WHERE "webhookKey"=:key0webhookKey '
            'DELETE FROM webhook_keys WHERE "webhookKey"=:key1webhookKey '
            'DELETE FROM scaling_policies WHERE "tenantId" = :tenantId AND '
            '"groupId" = :groupId AND "policyId" = :policyId '
            'DELETE FROM policy_webhooks WHERE "tenantId" = :tenantId AND '
            '"groupId" = :groupId AND "policyId" = :policyId '
            'APPLY BATCH;')
        expected_data = {
            "tenantId": self.group.tenant_id,
            "groupId": self.group.uuid,
            "policyId": "3222",
            "key0webhookKey": 'w1',
            "key1webhookKey": 'w2'}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

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
        expectedCql = (
            'SELECT group_config, created_at, deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
    def test_add_webhooks_valid_policy_return_value(self, mock_get_policy):
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
            'SELECT COUNT(*) FROM policy_webhooks '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_params = {'tenantId': self.tenant_id,
                           'groupId': self.group_id,
                           'policyId': policy_id}

        expected_insert_cql = (
            'BEGIN BATCH '

            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", '
            '"webhookId", data, capability, "webhookKey") '
            'VALUES (:tenantId, :groupId, :policyId, '
            ':webhook0Id, :webhook0, :webhook0Capability, :webhook0Key) '

            'INSERT INTO webhook_keys("webhookKey", "tenantId", "groupId", '
            '"policyId") '
            'VALUES (:webhook0Key, :tenantId, :groupId, :policyId) '

            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", '
            '"webhookId", data, capability, "webhookKey") '
            'VALUES (:tenantId, :groupId, :policyId, :webhook1Id, :webhook1, '
            ':webhook1Capability, :webhook1Key) '

            'INSERT INTO webhook_keys("webhookKey", "tenantId", "groupId", '
            '"policyId") '
            'VALUES (:webhook1Key, :tenantId, :groupId, :policyId) '

            'APPLY BATCH;')

        # can't test the parameters, because they contain serialized JSON.
        # have to pull out the serialized JSON, load it as an object, and then
        # compare
        self.assertEqual(
            self.connection.execute.mock_calls,
            [mock.call(expected_count_cql, expected_params,
                       ConsistencyLevel.QUORUM),
             mock.call(expected_insert_cql, mock.ANY,
                       ConsistencyLevel.QUORUM)])

        cql_params = self.connection.execute.call_args[0][1]

        for name in ('webhook0', 'webhook1'):
            cql_params[name] = json.loads(cql_params[name])
            capability_name = '{0}Capability'.format(name)
            cql_params[capability_name] = json.loads(
                cql_params[capability_name])

        expected_params.update({
            "webhook0Id": '100001',
            "webhook0": {'name': 'a name', 'metadata': {}, '_ver': 1},
            "webhook0Capability": {"ver": "hash", "_ver": 1},
            "webhook0Key": "hash",
            "webhook1Id": '100002',
            "webhook1": {'name': 'new name',
                         'metadata': {'k': 'v'},
                         '_ver': 1},
            "webhook1Capability": {"ver": "hash",
                                   "_ver": 1},
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
            'SELECT COUNT(*) FROM policy_webhooks '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id,
                         'policyId': policy_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

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
            'SELECT COUNT(*) FROM policy_webhooks '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId AND "policyId" = :policyId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id,
                         'policyId': policy_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

    def test_naive_list_all_webhooks(self):
        """
        Listing all webhooks from `_naive_list_all_webhooks` makes the right
        query.
        """
        self.returns = [[{'webhookId': 'w1'}]]
        d = self.group._naive_list_all_webhooks()

        self.assertEqual(self.successResultOf(d), [{'webhookId': 'w1'}])
        exp_cql = ('SELECT * FROM policy_webhooks '
                   'WHERE "tenantId" = :tenantId '
                   'AND "groupId" = :groupId '
                   'ORDER BY "groupId", "policyId", "webhookId";')
        self.connection.execute.assert_called_once_with(
            exp_cql, {'tenantId': self.tenant_id, 'groupId': self.group_id},
            ConsistencyLevel.QUORUM)

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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)
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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

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
            expectedCql, mock.ANY, ConsistencyLevel.QUORUM)

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
                return_value=defer.fail(
                    NoSuchWebhookError('t', 'g', 'p', 'w')))
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
        expectedCql = ('BEGIN BATCH '

                       'DELETE FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND "webhookId" = :webhookId '

                       'DELETE FROM webhook_keys '
                       'WHERE "webhookKey"=:webhookKey '

                       'APPLY BATCH;')
        expectedData = {"tenantId": "11111",
                        "groupId": "12345678g",
                        "policyId": "3444",
                        "webhookId": "4555",
                        'webhookKey': 'h'}

        self.assertEqual(len(self.connection.execute.mock_calls),
                         2)  # view, delete
        self.connection.execute.assert_called_with(expectedCql,
                                                   expectedData,
                                                   ConsistencyLevel.QUORUM)

    def test_delete_non_existant_webhooks(self):
        """
        If you try to delete a scaling policy webhook that doesn't exist,
        :class:`NoSuchWebhookError` is raised
        """
        self.returns = [[], None]
        d = self.group.delete_webhook('3444', '4555')
        self.failureResultOf(d, NoSuchWebhookError)
        self.assertEqual(len(self.connection.execute.mock_calls),
                         1)  # only view
        self.flushLoggedErrors(NoSuchWebhookError)

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
        # locks znode is not deleted
        self.assertFalse(self.kz_client.delete.called)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks')
    def test_delete_empty_scaling_group_with_policies(self, mock_naive,
                                                      mock_view_state):
        """
        ``delete_group`` deletes config, launch config, state, and the group's
        policies and webhooks if the scaling group is empty.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed(
            [{'webhookKey': 'w1'}, {'webhookKey': 'w2'}])

        self.returns = [None]
        self.clock.advance(34.575)
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id,
                         'ts': 34575000,
                         'key0webhookKey': 'w1',
                         'key1webhookKey': 'w2'}
        expected_cql = (
            'BEGIN BATCH '

            'DELETE FROM webhook_keys WHERE "webhookKey"=:key0webhookKey '

            'DELETE FROM webhook_keys WHERE "webhookKey"=:key1webhookKey '

            'DELETE FROM scaling_policies '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM policy_webhooks '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM scaling_group USING TIMESTAMP :ts '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

        self.kz_client.Lock.assert_called_once_with(
            '/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        self.lock.release.assert_called_once_with()
        self.kz_client.delete.assert_called_once_with(
            '/locks/' + self.group.uuid)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks')
    def test_delete_empty_scaling_group_with_zero_policies(self, mock_naive,
                                                           mock_view_state):
        """
        ``delete_group`` deletes config, launch config, state, and the group's
        policies and webhooks but not events if the scaling group is empty but
        has no policies.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed([])

        self.returns = [None]
        self.clock.advance(34.575)
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None
        mock_naive.assert_called_once_with()

        expected_data = {'tenantId': self.tenant_id,
                         'groupId': self.group_id,
                         'ts': 34575000}
        expected_cql = (
            'BEGIN BATCH '

            'DELETE FROM scaling_policies '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM policy_webhooks '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM scaling_group USING TIMESTAMP :ts '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

        self.kz_client.Lock.assert_called_once_with(
            '/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        self.lock.release.assert_called_once_with()
        self.kz_client.delete.assert_called_once_with(
            '/locks/' + self.group.uuid)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_not_acquired(self, mock_view_state):
        """
        If the lock is not acquired, do not delete the group.
        """
        self.lock.acquire.side_effect = \
            lambda timeout: defer.fail(ValueError('a'))

        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, 'a', {}, {}, None, {}, False))

        d = self.group.delete_group()
        self.failureResultOf(d, ValueError)

        self.assertFalse(self.connection.execute.called)
        self.kz_client.Lock.assert_called_once_with(
            '/locks/' + self.group.uuid)
        self.lock._acquire.assert_called_once_with(timeout=120)
        # locks znode is not deleted
        self.assertFalse(self.kz_client.delete.called)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_with_log_category_locking(self, mock_view_state):
        """
        The lock is created with log with category as locking
        """
        log = self.group.log = mock.Mock()

        self.group.delete_group()

        log.bind.assert_called_once_with(
            system='CassScalingGroup.delete_group')
        log.bind().bind.assert_called_once_with(category='locking')
        self.assertEqual(log.bind().bind().msg.call_count, 4)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks')
    def test_delete_group_successful_but_deleting_znode_fails(self, mock_naive,
                                                              mock_view_state):
        """
        ``delete_group``, if the rest is successful, attempts to delete the
        lock znode but if that fails, succeeds anyway, while retrying to delete
        the lock asynchronously.  If it never succeeds, an error is logged.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False))
        mock_naive.return_value = defer.succeed([])
        called = []

        def not_empty_error(lockpath):
            called.append(0)
            self.assertEqual(lockpath, '/locks/' + self.group.uuid)
            return defer.fail(NotEmptyError((), {}))

        self.kz_client.delete.side_effect = not_empty_error

        self.returns = [None]
        self.clock.advance(34.575)
        result = self.successResultOf(self.group.delete_group())
        for i in range(70):
            self.clock.advance(5)

        self.assertIsNone(result)  # delete returns None
        self.assertEqual(len(called), 61)
        self.group.log.msg.assert_called_with(
            "Error cleaning up lock path (when deleting group)",
            exc=matches(IsInstance(NotEmptyError)),
            otter_msg_type="ignore-delete-lock-error")


class ViewManifestTests(CassScalingGroupTestCase):
    """
    Tests for :func:`view_manifest`
    """

    def setUp(self):
        """
        Mock verified view
        """
        super(ViewManifestTests, self).setUp()
        self.verified_view = patch(self, 'otter.models.cass.verified_view')
        self.vv_return = {
            'tenantId': self.tenant_id,
            "groupId": self.group_id,
            'id': "12345678g",
            'group_config': serialize_json_data(self.config, 1.0),
            'launch_config': serialize_json_data(self.launch_config, 1.0),
            'active': '{"A":"R"}',
            'pending': '{"P":"R"}',
            'groupTouched': '2014-01-01T00:00:05Z.1234',
            'policyTouched': '{"PT":"R"}',
            'paused': False,
            'desired': 0,
            'created_at': 23
        }
        self.manifest = {
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch_config,
            'id': "12345678g",
            'state': GroupState(
                self.tenant_id,
                self.group_id,
                'a', {'A': 'R'},
                {'P': 'R'}, '2014-01-01T00:00:05Z.1234',
                {'PT': 'R'}, False)
        }
        self.group._naive_list_policies = mock.Mock()
        self.group._naive_list_all_webhooks = mock.Mock()

    def test_success(self):
        """
        When viewing the manifest, if the group exists a dictionary with the
        config, launch config, and scaling policies is returned.
        """
        self.verified_view.return_value = defer.succeed(self.vv_return)
        self.group._naive_list_policies.return_value = defer.succeed([])

        self.manifest['scalingPolicies'] = []
        self.assertEqual(
            self.validate_view_manifest_return_value(), self.manifest)

        self.group._naive_list_policies.assert_called_once_with()

        view_cql = (
            'SELECT "tenantId", "groupId", group_config, launch_config, '
            'active, pending, "groupTouched", "policyTouched", paused, '
            'desired, created_at, status, deleting '
            'FROM scaling_group '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId')
        del_cql = ('DELETE FROM scaling_group '
                   'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        exp_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}
        self.verified_view.assert_called_once_with(
            self.connection, view_cql, del_cql,
            exp_data, ConsistencyLevel.QUORUM,
            matches(IsInstance(NoSuchScalingGroupError)),
            self.mock_log, get_deleting=False)

    def test_with_webhooks(self):
        """
        Viewing manifest with_webhooks=True returns webhooks inside policies
        that matches the `model_schemas.manifest`
        """
        self.verified_view.return_value = defer.succeed(self.vv_return)

        # Getting policies
        policies = group_examples.policy()[:3]
        [policy.update({'id': str(i)}) for i, policy in enumerate(policies)]
        self.group._naive_list_policies.return_value = defer.succeed(policies)

        # Getting webhooks
        wh_part = {'data': '{"name": "a", "metadata": {"a": "b"}}',
                   'capability': '{"version": "v1"}'}
        webhooks = [{'policyId': '0', 'webhookId': '11'},
                    {'policyId': '0', 'webhookId': '12'},
                    {'policyId': '2', 'webhookId': '21'},
                    {'policyId': '2', 'webhookId': '22'},
                    {'policyId': '2', 'webhookId': '23'}]
        [webhook.update(wh_part) for webhook in webhooks]
        self.group._naive_list_all_webhooks.return_value = defer.succeed(
            webhooks)

        # Getting the result and comparing
        resp = self.validate_view_manifest_return_value(with_webhooks=True)
        exp_policies = deepcopy(policies)
        exp_policies[0]['webhooks'] = [
            _assemble_webhook_from_row(webhook, True)
            for webhook in webhooks[:2]]
        exp_policies[1]['webhooks'] = []
        exp_policies[2]['webhooks'] = [
            _assemble_webhook_from_row(webhook, True)
            for webhook in webhooks[2:]]
        self.manifest['scalingPolicies'] = exp_policies
        self.assertEqual(resp, self.manifest)

    @mock.patch('otter.models.cass.assemble_webhooks_in_policies')
    def test_no_policies(self, mock_awip):
        """
        Viewing manifest ``with_policies=False`` returns a manifest view with
        no policies and no webhooks, even though ``with_webhooks=True``.
        """
        self.verified_view.return_value = defer.succeed(self.vv_return)

        # Getting the result and comparing
        resp = self.validate_view_manifest_return_value(with_policies=False,
                                                        with_webhooks=True)
        self.assertEqual(resp, self.manifest)

        self.assertFalse(mock_awip.called)
        self.assertFalse(self.group._naive_list_policies.called)
        self.assertFalse(self.group._naive_list_all_webhooks.called)

    def test_with_deleting(self):
        """
        Viewing manifest ``get_deleting=True`` returns a manifest view with
        group status in it even if the group is deleting
        """
        self.vv_return['status'] = 'ERROR'
        self.vv_return['deleting'] = True
        self.verified_view.return_value = defer.succeed(self.vv_return)

        # Getting the result and comparing
        resp = self.validate_view_manifest_return_value(with_policies=False,
                                                        get_deleting=True)
        self.manifest['status'] = 'DELETING'
        self.assertEqual(resp, self.manifest)

        # verified_view called with `get_deleting=True`
        view_cql = (
            'SELECT "tenantId", "groupId", group_config, launch_config, '
            'active, pending, "groupTouched", "policyTouched", paused, '
            'desired, created_at, status, deleting '
            'FROM scaling_group '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId')
        del_cql = ('DELETE FROM scaling_group '
                   'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
        exp_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}
        self.verified_view.assert_called_once_with(
            self.connection, view_cql, del_cql,
            exp_data, ConsistencyLevel.QUORUM,
            matches(IsInstance(NoSuchScalingGroupError)),
            self.mock_log, get_deleting=True)

    def _check_with_deleting(self, status):
        self.verified_view.return_value = defer.succeed(self.vv_return)
        resp = self.validate_view_manifest_return_value(with_policies=False,
                                                        get_deleting=True)
        self.manifest['status'] = status
        self.assertEqual(resp, self.manifest)

    def test_with_deleting_normal_group(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including status when group is not deleting
        """
        self.vv_return['status'] = 'ACTIVE'
        self.vv_return['deleting'] = None
        self._check_with_deleting('ACTIVE')

    def test_with_deleting_none_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ACTIVE status when group is not deleting and status is None
        """
        self.vv_return['status'] = None
        self.vv_return['deleting'] = None
        self._check_with_deleting('ACTIVE')

    def test_with_deleting_disabled_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ERROR status when group is not deleting and status is
        DISABLED
        """
        self.vv_return['status'] = 'DISABLED'
        self.vv_return['deleting'] = None
        self._check_with_deleting('ERROR')

    def test_with_deleting_error_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ERROR status when group is not deleting and status is
        ERROR
        """
        self.vv_return['status'] = 'ERROR'
        self.vv_return['deleting'] = None
        self._check_with_deleting('ERROR')

    def test_no_such_group(self):
        """
        When viewing the manifest, if the group doesn't exist
        ``NoSuchScalingGroupError`` is raised and the policies is never
        retrieved.
        """
        self.verified_view.return_value = defer.fail(
            NoSuchScalingGroupError(2, 3))
        self.group._naive_list_policies = mock.MagicMock(
            return_value=defer.succeed('policies'))

        d = self.group.view_manifest()
        self.failureResultOf(d, NoSuchScalingGroupError)
        self.flushLoggedErrors()
        self.assertFalse(self.group._naive_list_policies.called)


class CassScalingGroupUpdatePolicyTests(CassScalingGroupTestCase):
    """
    Tests for `ScalingGroup.update_policy`
    """

    def setUp(self):
        """
        Mock `get_policy`
        """
        super(CassScalingGroupUpdatePolicyTests, self).setUp()
        self.get_policy = patch(
            self, 'otter.models.cass.CassScalingGroup.get_policy')

    def validate_policy_update(self, policy_json):
        """
        Validate CQL calls made to update the policy
        """
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '

            'APPLY BATCH;')
        expectedData = {"data": policy_json,
                        "groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111',
                        "version": "timeuuid"}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    def test_update_scaling_policy(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed({"type": "helvetica"})
        d = self.group.update_policy(
            '12345678', {"b": "lah", "type": "helvetica"})
        self.assertIsNone(self.successResultOf(d))  # update returns None
        self.validate_policy_update(
            '{"_ver": 1, "b": "lah", "type": "helvetica"}')

    def test_update_scaling_policy_schedule_no_change(self):
        """
        Schedule policy update with no args difference also updates
        scaling_schedule_v2 table.
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed(
            {"type": "schedule", "args": {"cron": "1 * * * *"}})
        d = self.group.update_policy(
            '12345678', {"type": "schedule", "args": {"cron": "1 * * * *"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, cron, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, '
            ':cron, :version) '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '

            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"cron": "1 * * * *"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g', "policyId": '12345678',
            "tenantId": '11111', "trigger": "next_time",
            "version": 'timeuuid', "bucket": 2, "cron": '1 * * * *'}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

    def test_update_scaling_policy_type_change(self):
        """
        Policy type cannot be changed while updating it
        """
        self.get_policy.return_value = defer.succeed({"type": "helvetica"})
        d = self.group.update_policy(
            '12345678', {"b": "lah", "type": "comicsans"})
        self.failureResultOf(d, ValidationError)
        self.assertFalse(self.connection.execute.called)

    def test_update_scaling_policy_at_schedule_change(self):
        """
        Updating at-style schedule policy updates respective entry in
        scaling_schedule_v2 table also
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed(
            {"type": "schedule",
             "args": {"at": "2013-07-30T19:03:12Z"}})
        d = self.group.update_policy(
            '12345678', {"type": "schedule",
                         "args": {"at": "2015-09-20T10:00:12Z"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, '
            ':version) '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '
            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"at": "2015-09-20T10:00:12Z"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g',
            "policyId": '12345678',
            "tenantId": '11111',
            "trigger": from_timestamp("2015-09-20T10:00:12Z"),
            "version": 'timeuuid',
            "bucket": 2}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

    def test_update_scaling_policy_cron_schedule_change(self):
        """
        Updating cron-style schedule policy updates respective entry in
        scaling_schedule_v2 table also
        """
        self.returns = [None]
        self.get_policy.return_value = defer.succeed(
            {"type": "schedule", "args": {"cron": "1 * * * *"}})
        d = self.group.update_policy(
            '12345678', {"type": "schedule", "args": {"cron": "2 0 * * *"}})
        self.assertIsNone(self.successResultOf(d))
        expected_cql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, cron, version) '
            'VALUES (:bucket, :tenantId, :groupId, :policyId, :trigger, '
            ':cron, :version) '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policyId, :data, :version) '

            'APPLY BATCH;')
        expected_data = {
            "data": '{"_ver": 1, "args": {"cron": "2 0 * * *"}, '
                    '"type": "schedule"}',
            "groupId": '12345678g', "policyId": '12345678',
            "tenantId": '11111', "trigger": "next_time",
            "version": 'timeuuid', "bucket": 2, "cron": '2 0 * * *'}
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

    def test_update_scaling_policy_bad(self):
        """
        Tests that if you try to update a scaling policy that doesn't exist,
        the right thing happens.
        """
        self.get_policy.return_value = defer.fail(
            NoSuchPolicyError('t', 'g', 'p'))
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
        self.view_config = patch(
            self, 'otter.models.cass.CassScalingGroup.view_config',
            return_value=defer.succeed({}))
        set_config_data(
            {'limits': {'absolute': {'maxPoliciesPerGroup': 1000}}})
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
            'SELECT COUNT(*) FROM scaling_policies '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

    def test_add_multiple_policies_overlimit(self):
        """
        If current policies + new policies will go over max policies, fail with
        PoliciesOverLimitError
        """
        self.returns = [[{'count': 998}]]
        d = self.group.create_policies([{"b": "lah"}] * 5)
        self.failureResultOf(d, PoliciesOverLimitError)

        expected_cql = (
            'SELECT COUNT(*) FROM scaling_policies '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" = :groupId;')
        expected_data = {'tenantId': self.tenant_id, 'groupId': self.group_id}

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

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

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, '
            ':policy0version) '

            'APPLY BATCH;')
        expectedData = {"policy0data": '{"_ver": 1, "b": "lah"}',
                        "policy0version": 'timeuuid',
                        "groupId": '12345678g',
                        "policy0policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        self.assertEqual(result, [{'b': 'lah',
                                   'id': self.mock_key.return_value}])

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_add_scaling_policy_at(self, mock_serial):
        """
        Test that you can add a scaling policy with 'at' schedule and what is
        returned is a list of the scaling policies with their ids
        """
        self.returns = [[{'count': 0}], None]
        expected_at = '2012-10-20T03:23:45'
        pol = {'cooldown': 5,
               'type': 'schedule',
               'name': 'scale up by 10',
               'change': 10,
               'args': {'at': expected_at}}

        d = self.group.create_policies([pol])

        result = self.successResultOf(d)
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, '
            ':policy0version) '

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", '
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
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        pol['id'] = self.mock_key.return_value
        self.assertEqual(result, [pol])

    def test_add_scaling_policy_cron(self):
        """
        Test that you can add a scaling policy with 'cron' schedule and what is
        returned is a list of the scaling policies with their ids
        """
        self.returns = [[{'count': 0}], None]
        pol = {'cooldown': 5,
               'type': 'schedule',
               'name': 'scale up by 10',
               'change': 10,
               'args': {'cron': '* * * * *'}}

        d = self.group.create_policies([pol])

        result = self.successResultOf(d)
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, '
            ':policy0version) '

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, cron, version) '
            'VALUES (:policy0bucket, :tenantId, :groupId, :policy0policyId, '
            ':policy0trigger, :policy0cron, :policy0version) '

            'APPLY BATCH;')
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policy0data": ('{"name": "scale up by 10", '
                                        '"args": {"cron": "* * * * *"}, '
                                        '"cooldown": 5, "_ver": 1, '
                                        '"type": "schedule", "change": 10}'),
                        "policy0policyId": '12345678',
                        "policy0trigger": 'next_time',
                        "policy0cron": "* * * * *",
                        "policy0bucket": 2,
                        "policy0version": "timeuuid"}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        pol['id'] = self.mock_key.return_value
        self.assertEqual(result, [pol])


class ScalingGroupWebhookMigrateTests(SynchronousTestCase):
    """
    Tests for webhook migration functions in :obj:`CassScalingGroup`
    """

    def setUp(self):
        """
        Sample CassScalingGroup object
        """
        self.store = CassScalingGroupCollection(None, None)

    def test_webhook_index_only(self):
        """
        `get_webhook_index_only` gets webhook info from policy_webhooks table
        and webhook_keys in parallel and returns those webhook info that is
        there in policy_webhooks table but NOT in webhook_keys table
        """
        eff = self.store.get_webhook_index_only()
        self.assertEqual(
            eff.intent,
            ParallelEffects([
                Effect(
                    CQLQueryExecute(
                        query=('SELECT "tenantId", "groupId", "policyId", '
                               '"webhookKey" FROM policy_webhooks'),
                        params={}, consistency_level=ConsistencyLevel.ONE)),
                Effect(
                    CQLQueryExecute(
                        query=('SELECT "tenantId", "groupId", "policyId", '
                               '"webhookKey" FROM webhook_keys'),
                        params={}, consistency_level=ConsistencyLevel.ONE))]))
        r = resolve_effect(
            eff, [[{'w1': '1'}, {'w2': '2'}], [{'w1': '1'}]])
        self.assertEqual(r, set(freeze([{'w2': '2'}])))

    def test_add_webhook_keys(self):
        """
        `add_webhook_keys` inserts webhook keys as a batch
        """
        eff = self.store.add_webhook_keys(
            [{'tenantId': 't1', 'groupId': 'g1', 'policyId': 'p1',
              'webhookKey': 'w1'},
             {'tenantId': 't2', 'groupId': 'g2', 'policyId': 'p2',
              'webhookKey': 'w2'}])

        query = (
            'BEGIN BATCH '
            'INSERT INTO webhook_keys ("tenantId", "groupId", "policyId", '
            '"webhookKey")'
            'VALUES (:tenantId0, :groupId0, :policyId0, :webhookKey0) '
            'INSERT INTO webhook_keys ("tenantId", "groupId", "policyId", '
            '"webhookKey")'
            'VALUES (:tenantId1, :groupId1, :policyId1, :webhookKey1) '
            'APPLY BATCH;')
        params = {
            'tenantId0': 't1', 'groupId0': 'g1', 'policyId0': 'p1',
            'webhookKey0': 'w1', 'tenantId1': 't2', 'groupId1': 'g2',
            'policyId1': 'p2', 'webhookKey1': 'w2'}
        self.assertEqual(
            eff.intent,
            CQLQueryExecute(query=query, params=params,
                            consistency_level=ConsistencyLevel.ONE))


class WebhookHashEffectTests(SynchronousTestCase):
    """
    Tests for :func:`webhook_by_hash_effect`
    """
    def setUp(self):
        self.log = mock_log()
        self.ch = 'h' * 64

    def _get_intent(self, query):
        return CQLQueryExecute(
            query=query, params={'webhookKey': self.ch},
            consistency_level=ConsistencyLevel.ONE)

    def test_not_64_len(self):
        """
        Raises error if cap_hash is not 64 chars
        """
        self.assertRaises(
            UnrecognizedCapabilityError, webhook_by_hash_effect,
            self.log, 'hash', 'wk', 'pw')
        self.assertRaises(
            UnrecognizedCapabilityError, webhook_by_hash_effect,
            self.log, 'ha' * 65, 'wk', 'pw')

    def test_from_keys_table(self):
        """
        Returns info from keys table if found and does not check webhooks table
        Does not log err
        """
        eff = webhook_by_hash_effect(self.log, self.ch, 'wk', 'pw')
        disp = SequenceDispatcher(
            [(self._get_intent(
                'SELECT "tenantId", "groupId", "policyId" FROM wk '
                'WHERE "webhookKey" = :webhookKey;'),
              lambda i: [
                  {'tenantId': 't1', 'groupId': 'g1', 'policyId': 'p1'}])])
        self.assertEqual(sync_perform(disp, eff), ('t1', 'g1', 'p1'))
        self.assertFalse(self.log.err.called)

    def test_from_webhooks_table(self):
        """
        If info is not found in keys table, finds info in webhooks table
        and logs error
        """
        eff = webhook_by_hash_effect(self.log, self.ch, 'wk', 'pw')
        disp = SequenceDispatcher(
            [(self._get_intent(
                'SELECT "tenantId", "groupId", "policyId" FROM wk '
                'WHERE "webhookKey" = :webhookKey;'),
              lambda i: raise_(UnrecognizedCapabilityError(self.ch, 1))),
             (self._get_intent(
                'SELECT "tenantId", "groupId", "policyId" FROM pw '
                'WHERE "webhookKey" = :webhookKey;'),
              lambda i: [
                  {'tenantId': 't1', 'groupId': 'g1', 'policyId': 'p1'}])])
        self.assertEqual(sync_perform(disp, eff), ('t1', 'g1', 'p1'))
        self.log.err.assert_called_once_with(
            None,
            ('Webhook hash not in webhook_keys table but in '
             'policy_webhooks table'))

    def test_not_found(self):
        """
        It tries the keys table and if not found tries the webhooks table
        and if not found raises error
        """
        eff = webhook_by_hash_effect(self.log, self.ch, 'wk', 'pw')
        disp = SequenceDispatcher(
            [(self._get_intent(
                'SELECT "tenantId", "groupId", "policyId" FROM wk '
                'WHERE "webhookKey" = :webhookKey;'),
              lambda i: raise_(UnrecognizedCapabilityError(self.ch, 1))),
             (self._get_intent(
                'SELECT "tenantId", "groupId", "policyId" FROM pw '
                'WHERE "webhookKey" = :webhookKey;'),
              lambda i: raise_(UnrecognizedCapabilityError(self.ch, 1)))])
        self.assertRaises(
            UnrecognizedCapabilityError, sync_perform, disp, eff)
        self.assertFalse(self.log.err.called)


class CassScalingScheduleCollectionTestCase(
        IScalingScheduleCollectionProviderMixin, SynchronousTestCase):
    """
    Tests for :class:`CassScalingScheduleCollection`
    """

    def setUp(self):
        """
        Setup the mocks.
        """
        self.connection = mock.MagicMock(spec=['execute'])

        self.returns = [None]

        def _responses(*args):
            result = _de_identify(self.returns.pop(0))
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.clock = Clock()
        self.collection = CassScalingGroupCollection(
            self.connection, self.clock)

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

    def test_fetch_and_delete(self):
        """
        Tests that you can fetch and delete list of events
        """
        self.returns = [[{'tenantId': '1d2',
                          'groupId': 'gr2',
                          'policyId': 'ef',
                          'trigger': 100,
                          'cron': 'c1',
                          'version': 'uuid1'},
                         {'tenantId': '1d2',
                          'groupId': 'gr2',
                          'policyId': 'ex',
                          'trigger': 122,
                          'cron': 'c2',
                          'version': 'uuid2'}],
                        None]
        events = self.returns[0]

        fetch_data = {'bucket': 2, 'now': 1234, 'size': 100}
        fetch_cql = (
            'SELECT "tenantId", "groupId", "policyId", "trigger", '
            'cron, version '
            'FROM scaling_schedule_v2 '
            'WHERE bucket = :bucket AND trigger <= :now LIMIT :size;')
        del_cql = ('BEGIN BATCH '

                   'DELETE FROM scaling_schedule_v2 '
                   'WHERE bucket = :bucket '
                   'AND trigger = :event0trigger '
                   'AND "policyId" = :event0policyId; '

                   'DELETE FROM scaling_schedule_v2 '
                   'WHERE bucket = :bucket '
                   'AND trigger = :event1trigger '
                   'AND "policyId" = :event1policyId; '

                   'APPLY BATCH;')
        del_data = {'bucket': 2, 'event0trigger': 100, 'event0policyId': 'ef',
                    'event1trigger': 122, 'event1policyId': 'ex'}

        result = self.validate_fetch_and_delete(2, 1234, 100)

        self.assertEqual(result, events)
        self.assertEqual(
            self.connection.execute.mock_calls,
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

            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, cron, version) '
            'VALUES (:event0bucket, :event0tenantId, :event0groupId, '
            ':event0policyId, :event0trigger, :event0cron, :event0version); '
            'INSERT INTO scaling_schedule_v2(bucket, "tenantId", "groupId", '
            '"policyId", trigger, cron, version) '
            'VALUES (:event1bucket, :event1tenantId, :event1groupId, '
            ':event1policyId, :event1trigger, :event1cron, :event1version); '

            'APPLY BATCH;')
        data = {'event0bucket': 2,
                'event0tenantId': '1d2',
                'event0groupId': 'gr2',
                'event0policyId': 'ef',
                'event0trigger': 100,
                'event0cron': 'c1',
                'event0version': 'v1',

                'event1bucket': 3,
                'event1tenantId': '1d3',
                'event1groupId': 'gr3',
                'event1policyId': 'ex',
                'event1trigger': 122,
                'event1cron': 'c2',
                'event1version': 'v2'}
        self.collection.buckets = iter(range(2, 4))

        result = self.successResultOf(self.collection.add_cron_events(events))
        self.assertEqual(result, None)
        self.connection.execute.assert_called_once_with(
            cql, data, ConsistencyLevel.ONE)

    def test_get_oldest_event(self):
        """
        Tests for `get_oldest_event`
        """
        events = [{'tenantId': '1d2', 'groupId': 'gr2', 'policyId': 'ef',
                   'trigger': 100, 'cron': 'c1', 'version': 'v1'}]
        self.returns = [events]

        d = self.collection.get_oldest_event(2)

        self.assertEqual(self.successResultOf(d), events[0])
        self.connection.execute.assert_called_once_with(
            'SELECT * from scaling_schedule_v2 WHERE bucket=:bucket LIMIT 1;',
            {'bucket': 2}, ConsistencyLevel.ONE)

    def test_get_oldest_event_empty(self):
        """
        Tests for `get_oldest_event`
        """
        self.returns = [[]]

        d = self.collection.get_oldest_event(2)

        self.assertIsNone(self.successResultOf(d))


class CassScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          SynchronousTestCase):
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
        self.clock = Clock()

        self.collection = CassScalingGroupCollection(self.connection,
                                                     self.clock)

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

        self.uuid = patch(self, 'otter.models.cass.uuid')
        self.uuid.uuid1.return_value = 'timeuuid'

        # 'serializing' something just wraps it with a _S
        self.mock_serial = patch(self, 'otter.models.cass.serialize_json_data',
                                 side_effect=lambda *args: _S(args[0]))

        self.group = {
            'tenantId': '123',
            'groupId': 'group',
            'group_config': '{"name": "test"}',
            'active': '{}',
            'pending': '{}',
            'groupTouched': None,
            'policyTouched': '{}',
            'paused': False,
            'desired': 0,
            'created_at': 23,
            'deleting': False
        }

    @mock.patch('otter.models.cass.WeakLocks', return_value=2)
    def test_locks(self, mock_wl):
        """
        `CassScalingGroupCollection` keeps new WeakLocks object
        """
        collection = CassScalingGroupCollection(self.connection, self.clock)
        mock_wl.assert_called_once_with()
        self.assertEqual(collection.local_locks, 2)

    def test_create(self):
        """
        Test that you can create a group, and if successful the group ID is
        returned
        """
        self.clock.advance(10.345)
        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "policyTouched": '{}',
            "paused": False,
            "desired": 0,
            "ts": 10345000}
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
            'launch_config, active, pending, "policyTouched", '
            'paused, desired, created_at) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at) '
            'USING TIMESTAMP :ts '

            'APPLY BATCH;')
        self.mock_key.return_value = '12345678'

        result = self.validate_create_return_value(self.mock_log, '123',
                                                   self.config, self.launch)

        self.assertEqual(result['groupConfiguration'], self.config)
        self.assertEqual(result['scalingPolicies'], [])
        self.assertEqual(result['launchConfiguration'], self.launch)
        self.assertEqual(result['id'], self.mock_key.return_value)
        self.assertTrue(isinstance(result['state'], GroupState))

        # Verify data argument seperately since data in actual call will have
        # datetime.utcnow which cannot be mocked or predicted.
        data = self.connection.execute.call_args[0][1]
        self.assertTrue(isinstance(data.pop('created_at'), datetime))
        self.assertEqual(expectedData, data)

        self.connection.execute.assert_called_with(expectedCql,
                                                   mock.ANY,
                                                   ConsistencyLevel.QUORUM)

    def test_create_with_policy(self):
        """
        Test that you can create a scaling group with a single policy, and if
        successful the group ID is returned
        """
        policy = group_examples.policy()[0]

        self.clock.advance(10.567)
        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '12345678',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "desired": 0,
            "ts": 10567000,
            "policyTouched": '{}',
            "paused": False,
            'policy0policyId': '12345678',
            'policy0data': _S(policy),
            'policy0version': 'timeuuid'}
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
            'launch_config, active, pending, "policyTouched", paused, '
            'desired, created_at) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at) '
            'USING TIMESTAMP :ts '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, '
            ':policy0version) '

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
                                                   ConsistencyLevel.QUORUM)

    def test_create_with_policy_multiple(self):
        """
        Test that you can create a scaling group with multiple policies, and if
        successful the group ID is returned
        """
        policies = group_examples.policy()[:2]

        self.clock.advance(10.466)
        expectedData = {
            'group_config': _S(self.config),
            'launch_config': _S(self.launch),
            'groupId': '1',
            'tenantId': '123',
            "active": '{}',
            "pending": '{}',
            "policyTouched": '{}',
            "paused": False,
            "desired": 0,
            "ts": 10466000,
            'policy0policyId': '2',
            'policy0data': _S(policies[0]),
            'policy0version': 'timeuuid',
            'policy1policyId': '3',
            'policy1data': _S(policies[1]),
            'policy1version': 'timeuuid'}
        expectedCql = (
            'BEGIN BATCH '

            'INSERT INTO scaling_group("tenantId", "groupId", group_config, '
            'launch_config, active, pending, "policyTouched", paused, '
            'desired, created_at) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at) '
            'USING TIMESTAMP :ts '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy0policyId, :policy0data, '
            ':policy0version) '

            'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
            'data, version) '
            'VALUES (:tenantId, :groupId, :policy1policyId, :policy1data, '
            ':policy1version) '

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
                                                   ConsistencyLevel.QUORUM)

    def test_max_groups_underlimit(self):
        """
        test scaling group creation when below maxGroups limit
        """
        self.returns = [[{'count': 1}], None]

        expectedData = {'tenantId': '1234'}
        expectedCQL = ('SELECT COUNT(*) FROM scaling_group '
                       'WHERE "tenantId" = :tenantId;')

        d = self.collection.create_scaling_group(
            mock.Mock(), '1234', self.config, self.launch)
        self.assertTrue(isinstance(self.successResultOf(d), dict))

        self.assertEqual(len(self.connection.execute.mock_calls), 2)
        self.assertEqual(
            self.connection.execute.mock_calls[0],
            mock.call(expectedCQL, expectedData, ConsistencyLevel.QUORUM))

    def test_max_groups_overlimit(self):
        """
        test scaling group creation when at maxGroups limit
        """
        set_config_data({'limits': {'absolute': {'maxGroups': 1}}})
        self.returns = [[{'count': 1}]]

        expectedData = {'tenantId': '1234'}
        expectedCQL = (
            'SELECT COUNT(*) FROM scaling_group '
            'WHERE "tenantId" = :tenantId;')

        d = self.collection.create_scaling_group(
            mock.Mock(), '1234', self.config, self.launch)
        self.connection.execute.assert_called_once_with(
            expectedCQL, expectedData, ConsistencyLevel.QUORUM)

        self.failureResultOf(d, ScalingGroupOverLimitError)

    def test_list_states(self):
        """
        ``list_scaling_group_states`` returns a list of :class:`GroupState`
        objects from cassandra
        """
        self.returns = [[assoc(self.group, 'groupId', 'group{}'.format(i))
                         for i in range(2)]]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        def group_state_with_id(group_id):
            group_state = GroupState(tenant_id='123',
                                     group_id=group_id,
                                     group_name='test',
                                     active={},
                                     pending={},
                                     group_touched='0001-01-01T00:00:00Z',
                                     policy_touched={},
                                     paused=False)
            return group_state

        self.assertEqual(r, [group_state_with_id("group0"),
                             group_state_with_id("group1")])

    def test_list_empty(self):
        """
        If there are no states in cassandra, ``list_scaling_group_states``
        returns an empty list
        """
        self.returns = [[]]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, '
            'created_at, deleting '
            'FROM scaling_group WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(r, [])
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    def test_list_states_respects_limit(self):
        """
        If there are more than the requested number of states,
        ``list_scaling_group_states`` only requests the requested number.
        """
        self.returns = [[]]
        expectedData = {'tenantId': '123', 'limit': 5}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId '
            'LIMIT :limit;')
        self.collection.list_scaling_group_states(
            self.mock_log, '123', limit=5)
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    def test_list_states_offsets_by_marker(self):
        """
        If a marker is provided, it is passed into the CQL as a where clause.
        """
        self.returns = [[]]
        expectedData = {'tenantId': '123', 'limit': 100, 'marker': '345'}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId '
            'AND "groupId" > :marker LIMIT :limit;')
        self.collection.list_scaling_group_states(self.mock_log, '123',
                                                  marker='345')
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    def test_list_states_does_not_return_resurrected_groups(self):
        """
        If any of the rows returned is resurrected, i.e. does not contain
        created_at then it is not returned.
        """
        group1 = self.group.copy()
        group1['groupId'] = 'group123'
        group2 = self.group.copy()
        group2['tenantId'] = '23'
        group2['groupId'] = 'group23'
        group2['created_at'] = None
        self.returns = [[group1, group2], None]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'deleting FROM scaling_group '
            'WHERE "tenantId" = :tenantId LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(
            self.connection.execute.call_args_list[0],
            mock.call(expectedCql, expectedData, ConsistencyLevel.QUORUM))
        self.assertEqual(r, [GroupState(tenant_id='123',
                                        group_id='group123',
                                        group_name='test',
                                        active={},
                                        pending={},
                                        group_touched='0001-01-01T00:00:00Z',
                                        policy_touched={},
                                        paused=False)])
        self.mock_log.msg.assert_called_once_with(
            'Resurrected rows',
            tenant_id='123',
            rows=[_de_identify(group2)])

    def test_list_states_deletes_resurrected_groups(self):
        """
        If any of the rows returned is resurrected, i.e. does not contain
        created_at, then it is triggered for deletion.
        """
        g1 = self.group.copy()
        g1['groupId'] = 'group123'
        groups = [g1]
        for i in range(4, 6):
            g = self.group.copy()
            g['groupId'] = 'group12{}'.format(i)
            g['created_at'] = None
            groups.append(g)
        self.returns = [groups, None]

        expectedCql = ('BEGIN BATCH '

                       'DELETE FROM scaling_group '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId0 '

                       'DELETE FROM scaling_group '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId1 '

                       'DELETE FROM scaling_policies '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId0 '

                       'DELETE FROM scaling_policies '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId1 '

                       'DELETE FROM policy_webhooks '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId0 '

                       'DELETE FROM policy_webhooks '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId1 '

                       'APPLY BATCH;')
        expectedData = {'groupId0': 'group124',
                        'groupId1': 'group125',
                        'tenantId': '123'}
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(self.connection.execute.call_count, 2)
        self.assertEqual(
            self.connection.execute.call_args_list[1],
            mock.call(expectedCql, expectedData, ConsistencyLevel.QUORUM))
        self.assertEqual(r, [GroupState(tenant_id='123',
                                        group_id='group123',
                                        group_name='test',
                                        active={},
                                        pending={},
                                        group_touched='0001-01-01T00:00:00Z',
                                        policy_touched={},
                                        paused=False)])

    def _extract_execute_query(self, call):
        args, _ = call
        query, params, c = args
        return query

    def test_list_states_filters_deleting_groups(self):
        """
        Groups that are deleting based on "deleting" column to be true are not
        returned
        """
        g1 = self.group.copy()
        g1['groupId'] = 'group123'
        g2 = self.group.copy()
        g2['groupId'] = 'group124'
        g2['deleting'] = True
        self.returns = [[g1, g2], None]
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.assertEqual(r, [GroupState(tenant_id='123',
                                        group_id='group123',
                                        group_name='test',
                                        active={},
                                        pending={},
                                        group_touched='0001-01-01T00:00:00Z',
                                        policy_touched={},
                                        paused=False)])
        # No call to delete row was made
        self.assertEqual(len(self.connection.execute.call_args_list), 1)
        self.assertNotIn(
            'DELETE', self._extract_execute_query(
                self.connection.execute.call_args_list[0]))

    def test_get_scaling_group(self):
        """
        Tests that you can get a scaling group
        (note that it doesn't request the database), and the local locks and
        consistency information is passed from the collection to the group.
        """
        g = self.collection.get_scaling_group(self.mock_log, '123', '12345678')
        self.assertTrue(isinstance(g, CassScalingGroup))
        self.assertEqual(g.uuid, '12345678')
        self.assertEqual(g.tenant_id, '123')
        self.assertIs(g.local_locks, self.collection.local_locks)

    @mock.patch('otter.models.cass.perform')
    @mock.patch('otter.models.cass.get_cql_dispatcher')
    @mock.patch('otter.models.cass.webhook_by_hash_effect')
    def test_webhook_info_by_hash(self, mock_wbhe, mock_gqd, mock_p):
        """
        `webhook_info_by_hash` gets effect from `webhook_by_hash_effect`
        and performs it
        """
        # NOTE: This is gnarly
        d = self.collection.webhook_info_by_hash(self.mock_log, 'x')
        self.assertEqual(d, mock_p.return_value)
        mock_wbhe.assert_called_once_with(
            self.mock_log, 'x', 'webhook_keys', 'policy_webhooks')
        mock_gqd.assert_called_once_with(
            self.collection.reactor, self.collection.connection)
        mock_p.assert_called_once_with(
            mock_gqd.return_value, mock_wbhe.return_value)

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
        config_query = ('SELECT COUNT(*) FROM scaling_group '
                        'WHERE "tenantId" = :tenantId;')
        policy_query = ('SELECT COUNT(*) FROM scaling_policies '
                        'WHERE "tenantId" = :tenantId;')
        webhook_query = ('SELECT COUNT(*) FROM policy_webhooks '
                         'WHERE "tenantId" = :tenantId;')

        calls = [
            mock.call(config_query, expectedData, ConsistencyLevel.ONE),
            mock.call(policy_query, expectedData, ConsistencyLevel.ONE),
            mock.call(webhook_query, expectedData, ConsistencyLevel.ONE)]

        d = self.collection.get_counts(self.mock_log, '123')
        result = self.successResultOf(d)
        self.assertEquals(result, expectedResults)
        self.connection.execute.assert_has_calls(calls)


class CassScalingGroupsCollectionHealthCheckTestCase(
        IScalingGroupCollectionProviderMixin, LockMixin, SynchronousTestCase):
    """
    Tests for `health_check` and `kazoo_health_check` in
    :class:`CassScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock(spec=['execute'])
        self.connection.execute.return_value = defer.succeed([])
        self.clock = Clock()
        self.collection = CassScalingGroupCollection(self.connection,
                                                     self.clock)
        self.collection.kz_client = mock.MagicMock(connected=True,
                                                   state=KazooState.CONNECTED)
        self.lock = self.mock_lock()
        self.collection.kz_client.Lock.return_value = self.lock

    def test_kazoo_no_zookeeper(self):
        """
        Kazoo health check fails if there is no zookeeper client
        """
        self.collection.kz_client = None
        d = self.collection.kazoo_health_check()
        self.assertEqual(d, (False, {'reason': 'No client yet'}))

    def test_kazoo_zookeeper_not_connected(self):
        """
        Kazoo health check fails if there is no zookeeper client
        """
        self.collection.kz_client.connected = False
        d = self.collection.kazoo_health_check()
        self.assertEqual(d, (False, {'reason': 'Not connected yet'}))

    def test_kazoo_zookeeper_suspended(self):
        """
        Kazoo Health check fails if the zookeeper client state is not CONNECTED
        """
        self.collection.kz_client.state = KazooState.SUSPENDED
        d = self.collection.kazoo_health_check()
        self.assertEqual(d, (False, {'zookeeper_state': KazooState.SUSPENDED}))

    @mock.patch('otter.models.cass.uuid')
    def test_zookeeper_lock_acquired(self, mock_uuid):
        """
        Acquires sample lock and succeeds if it is able to acquire. Deletes the
        lock path before returning.
        """
        self.collection.kz_client.delete.return_value = defer.succeed(None)
        mock_uuid.uuid1.return_value = 'uuid1'

        d = self.collection.kazoo_health_check()

        self.assertEqual(self.successResultOf(d), (True, {'total_time': 0}))
        self.collection.kz_client.Lock.assert_called_once_with(
            '/locks/test_uuid1')
        self.lock._acquire.assert_called_once_with(timeout=5)
        self.lock.release.assert_called_once_with()
        self.collection.kz_client.delete.assert_called_once_with(
            '/locks/test_uuid1', recursive=True)

    @mock.patch('otter.models.cass.uuid')
    def test_zookeeper_lock_failed(self, mock_uuid):
        """
        Acquires sample lock and fails if it is not able to acquire.
        """
        self.lock._acquire.side_effect = \
            lambda timeout: defer.fail(ValueError('e'))
        mock_uuid.uuid1.return_value = 'uuid1'

        d = self.collection.kazoo_health_check()

        self.failureResultOf(d, ValueError)
        self.collection.kz_client.Lock.assert_called_once_with(
            '/locks/test_uuid1')
        self.lock._acquire.assert_called_once_with(timeout=5)
        self.assertFalse(self.lock.release.called)
        self.assertFalse(self.collection.kz_client.delete.called)

    def test_health_check_cassandra_fails(self):
        """
        Health check fails if cassandra fails
        """
        self.connection.execute.return_value = defer.fail(Exception('boo'))
        d = self.collection.health_check()
        f = self.failureResultOf(d, Exception)
        self.assertEqual(f.value.args, ('boo',))

    def test_health_check_cassandra_succeeds(self):
        """
        Health check fails if cassandra fails
        """
        d = self.collection.health_check()
        self.assertEqual(
            self.successResultOf(d),
            (True, {'cassandra_time': 0}))


class CassAdminTestCase(SynchronousTestCase):
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

        calls = [mock.call(config_query, {}, ConsistencyLevel.QUORUM),
                 mock.call(policy_query, {}, ConsistencyLevel.QUORUM),
                 mock.call(webhook_query, {},  ConsistencyLevel.QUORUM)]

        d = self.collection.get_metrics(self.mock_log)
        result = self.successResultOf(d)
        self.assertEquals(result, expectedResults)
        self.connection.execute.assert_has_calls(calls)
