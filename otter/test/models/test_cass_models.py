"""
Tests for :mod:`otter.models.cass`
"""
import itertools
import json
from collections import namedtuple
from copy import deepcopy
from datetime import datetime
from functools import partial

from effect import (
    Constant, Effect, ParallelEffects, TypeDispatcher, sync_perform)
from effect.testing import perform_sequence, resolve_effect

from jsonschema import ValidationError

from kazoo.exceptions import NotEmptyError
from kazoo.protocol.states import KazooState

import mock

from pyrsistent import freeze

from silverberg.client import CQLClient, ConsistencyLevel

from testtools.matchers import IsInstance

from toolz.dicttoolz import assoc, merge

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from txeffect import deferred_performer

from otter.json_schema import group_examples
from otter.models.cass import (
    ACQUIRE_TIMEOUT,
    CQLQueryExecute,
    CassAdmin,
    CassScalingGroup,
    CassScalingGroupCollection,
    CassScalingGroupServersCache,
    WeakLocks,
    _assemble_webhook_from_row,
    assemble_webhooks_in_policies,
    cql_eff,
    get_cql_dispatcher,
    perform_cql_query,
    serialize_json_data,
    verified_view
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
from otter.test.util.test_zk import ZKCrudModel, create_fake_lock
from otter.test.utils import (
    DummyException,
    LockMixin,
    matches,
    mock_log,
    patch,
    test_dispatcher)
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


class EffectTests(SynchronousTestCase):
    """
    Tests for :func:`perform_cql_query` and :func:`get_cql_dispatcher`
    """

    def test_perform_cql_query(self):
        """
        `perform_cql_query` calls given connection's execute
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

    @mock.patch('otter.models.cass.perform_cql_query')
    def test_cql_disp(self, mock_pcq):
        """
        The :obj:`CQLQueryExecute` performer is called with
        dispatcher returned from get_cql_dispatcher
        """

        @deferred_performer
        def performer(c, d, i):
            return defer.succeed('p' + c)

        mock_pcq.side_effect = performer

        dispatcher = get_cql_dispatcher('conn')
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

    def _verified_view(self):
        """
        Returns a verified view, with some test arguments.
        """
        return verified_view(
            self.connection, 'vq', 'dq', {'d': 2}, ConsistencyLevel.TWO,
            ValueError, self.log)

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


scaling_group_entry = {
    'tenantId': 'tenant_id',
    "groupId": 'group_id',
    'id': "12345678g",
    'group_config': serialize_json_data({'name': 'a'}, 1.0),
    'launch_config': serialize_json_data({}, 1.0),
    'active': '{"A":"R"}',
    'pending': '{"P":"R"}',
    'groupTouched': '2014-01-01T00:00:05Z.1234',
    'policyTouched': '{"PT":"R"}',
    'paused': False,
    'desired': 0,
    'created_at': 23,
    'deleting': False,
    'status': 'ACTIVE',
    'error_reasons': [],
    'suspended': None
}


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

        self.kz_client = ZKCrudModel()
        self.kz_client.nodes = {"/locks/" + self.group_id: ("", 0)}

        self.acquire_call = (True, ACQUIRE_TIMEOUT, True)
        self.release_call = None

        def create_ZKLock(disp, path):
            self.assertEqual(disp, "dispatcher")
            self.assertEqual(path, "/locks/" + self.group_id)
            self.lb, lock = create_fake_lock(self.acquire_call,
                                             self.release_call)
            return lock

        from otter.models.cass import zk
        self.patch(zk, "PollingLock", create_ZKLock)

        self.clock = Clock()
        locks = WeakLocks()

        self.group = CassScalingGroup(self.mock_log,
                                      self.tenant_id,
                                      self.group_id,
                                      self.connection,
                                      itertools.cycle(range(2, 10)),
                                      self.kz_client,
                                      self.clock,
                                      locks,
                                      "dispatcher")
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

        r = f(2, 3)
        # Wrapped function's return is same
        self.assertEqual(r, 45)
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
        expectedCql = ('SELECT group_config, created_at '
                       'FROM scaling_group '
                       'WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND deleting=false;')
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
        view_cql = ('SELECT group_config, created_at '
                    'FROM scaling_group '
                    'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
                    'AND deleting=false;')
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
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'desired': 10,
                   'error_reasons': ['a', 'b']})
        ]]
        d = self.group.view_state()
        r = self.successResultOf(d)
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, launch_config, '
            'active, pending, "groupTouched", "policyTouched", paused, '
            'desired, created_at, status, error_reasons, deleting '
            'FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
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
                                 status=ScalingGroupStatus.ACTIVE,
                                 desired=10,
                                 error_reasons=['a', 'b'])
        self.assertEqual(r, group_state)

    def test_view_state_no_desired_capacity(self):
        """
        If there is no desired capacity, it defaults to 0
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'desired': None})
        ]]
        r = self.successResultOf(self.group.view_state())
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'},
                                       {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       False,
                                       ScalingGroupStatus.ACTIVE,
                                       desired=0))

    def test_view_state_suspended(self):
        """
        Gets suspended attr based on "suspended" column
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'suspended': True})
        ]]
        r = self.successResultOf(self.group.view_state())
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'},
                                       {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       False,
                                       ScalingGroupStatus.ACTIVE,
                                       desired=0,
                                       suspended=True))

    def test_view_respsects_consistency_argument(self):
        """
        If a consistency argument is passed to ``view_state``, it is honored
        over the default consistency
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id, 'groupId': self.group_id})
        ]]
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
        self.failureResultOf(self.group.view_state(), NoSuchScalingGroupError)

    def test_view_state_deleting_group_filter_deleting_group(self):
        """
        Calling ``view_state`` on a group that is deleting, with
        ``get_deleting`` = `False`, raises a :class:`NoSuchScalingGroupError`
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'deleting': True})
        ]]
        self.failureResultOf(self.group.view_state(), NoSuchScalingGroupError)

    def test_view_state_deleting_group_do_not_filter_deleting_group(self):
        """
        Calling ``view_state`` on a group that is deleting, with
        ``get_deleting`` = `True`, returns the deleting group
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'deleting': True})
        ]]
        result = self.successResultOf(self.group.view_state(get_deleting=True))
        group_state = GroupState(tenant_id=self.tenant_id,
                                 group_id=self.group_id,
                                 group_name='a',
                                 active={'A': 'R'},
                                 pending={'P': 'R'},
                                 group_touched='2014-01-01T00:00:05Z.1234',
                                 policy_touched={'PT': 'R'},
                                 paused=False,
                                 status=ScalingGroupStatus.DELETING,
                                 desired=0)
        self.assertEqual(result, group_state)

    def test_view_state_error_status(self):
        """
        view_state sets the ``GroupState.status`` based on the ``status``
        value.
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'desired': 10,
                   'status': 'ERROR'})
        ]]
        result = self.successResultOf(self.group.view_state())

        group_state = GroupState(tenant_id=self.tenant_id,
                                 group_id=self.group_id,
                                 group_name='a',
                                 active={'A': 'R'},
                                 pending={'P': 'R'},
                                 group_touched='2014-01-01T00:00:05Z.1234',
                                 policy_touched={'PT': 'R'},
                                 paused=False,
                                 status=ScalingGroupStatus.ERROR,
                                 desired=10)
        self.assertEqual(result, group_state)

    def test_view_state_recurrected_entry(self):
        """
        If group row returned is resurrected, i.e. does not have
        'created_at', then NoSuchScalingGroupError is returned and
        that row's deletion is triggered.
        """
        cass_response = [
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'created_at': None})
        ]
        self.returns = [cass_response, None]
        d = self.group.view_state()
        self.failureResultOf(d, NoSuchScalingGroupError)
        viewCql = (
            'SELECT "tenantId", "groupId", group_config, launch_config, '
            'active, pending, "groupTouched", "policyTouched", paused, '
            'desired, created_at, status, error_reasons, deleting '
            'FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
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
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'paused': True})
        ]]
        d = self.group.view_state()
        r = self.successResultOf(d)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'}, {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       True,
                                       ScalingGroupStatus.ACTIVE,
                                       desired=0))

    def test_view_state_no_error_reasons(self):
        """
        view_state with None error_reasons returns state with [] error_reasons
        """
        self.returns = [[
            merge(scaling_group_entry,
                  {'tenantId': self.tenant_id,
                   'groupId': self.group_id,
                   'error_reasons': None})
        ]]
        d = self.group.view_state()
        r = self.successResultOf(d)
        self.assertEqual(r, GroupState(self.tenant_id, self.group_id,
                                       'a',
                                       {'A': 'R'}, {'P': 'R'},
                                       '2014-01-01T00:00:05Z.1234',
                                       {'PT': 'R'},
                                       False,
                                       ScalingGroupStatus.ACTIVE,
                                       desired=0,
                                       error_reasons=[]))

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
                                     status=ScalingGroupStatus.ACTIVE,
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

        self.assertFalse(self.lb.acquired)

    def test_modify_state_local_lock_before_kz_lock(self):
        """
        ``modify_state`` first acquires local lock then acquires kz lock
        """
        modifier_d = defer.Deferred()
        group_state = GroupState(tenant_id=self.tenant_id,
                                 group_id=self.group_id,
                                 group_name='a',
                                 active={},
                                 pending={},
                                 group_touched=None,
                                 policy_touched={},
                                 paused=True,
                                 status=ScalingGroupStatus.ACTIVE,
                                 desired=5)

        def modifier(_group, _state):
            return modifier_d

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        llock = defer.DeferredLock()

        class Locks(object):
            def get_lock(lself, key):
                self.assertEqual(key, self.group_id)
                return llock

        # setup local lock
        self.group.local_locks = Locks()

        # setup local and kz lock acquire and release returns
        kz_acquire_d = defer.Deferred()
        self.acquire_call = (True, ACQUIRE_TIMEOUT, kz_acquire_d)
        kz_release_d = defer.Deferred()
        self.release_call = kz_release_d

        d = self.group.modify_state(modifier)

        self.assertNoResult(d)
        # local lock was acquired first then kz lock
        self.assertTrue(llock.locked)
        self.assertIs(self.lb.acquired, self.lb.NOT_STARTED)
        kz_acquire_d.callback(True)
        self.assertTrue(self.lb.acquired)
        # after modification kz lock is released then local lock
        modifier_d.callback(group_state)
        self.assertTrue(llock.locked)
        kz_release_d.callback(None)
        self.assertFalse(self.lb.acquired)
        self.assertFalse(llock.locked)
        self.assertEqual(self.successResultOf(d), None)

    @mock.patch('otter.models.cass.serialize_json_data',
                side_effect=lambda *args: _S(args[0]))
    def test_modify_state_lock_not_acquired(self, mock_serial):
        """
        ``modify_state`` raises error if lock is not acquired and does not
        do anything else
        """
        self.acquire_call = (True, ACQUIRE_TIMEOUT, Failure(ValueError("eh")))

        def modifier(group, state):
            raise

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        d = self.group.modify_state(modifier)
        self.failureResultOf(d, ValueError)
        self.assertEqual(self.connection.execute.call_count, 0)
        self.assertIs(self.lb.acquired, self.lb.NOT_STARTED)

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
                                     status=ScalingGroupStatus.ACTIVE,
                                     paused=True)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))
        self.returns = [None, None]
        log = self.group.log = mock.Mock()

        self.group.modify_state(modifier)

        log.bind.assert_called_once_with(
            modify_state_reason=None,
            system='CassScalingGroup.modify_state')
        log.bind().bind.assert_called_once_with(
            category='locking', lock_reason='modify_state')
        self.assertFalse(self.lb.acquired)

    def test_modify_state_propagates_modifier_error_and_does_not_save(self):
        """
        ``modify_state`` does not write anything to the db if the modifier
        raises an exception
        """
        def modifier(group, state):
            raise NoSuchScalingGroupError(self.tenant_id, self.group_id)

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.failureResultOf(d, NoSuchScalingGroupError)
        self.assertEqual(self.connection.execute.call_count, 0)
        self.assertFalse(self.lb.acquired)

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
                                     status=ScalingGroupStatus.ACTIVE,
                                     paused=True)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.failureResultOf(d, AssertionError)
        self.assertEqual(self.connection.execute.call_count, 0)
        self.assertFalse(self.lb.acquired)

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
                                     status=ScalingGroupStatus.ACTIVE,
                                     paused=True)
            return group_state

        self.group.view_state = mock.Mock(return_value=defer.succeed('state'))

        d = self.group.modify_state(modifier)
        self.failureResultOf(d, AssertionError)
        self.assertEqual(self.connection.execute.call_count, 0)
        self.assertFalse(self.lb.acquired)

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

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_update_error_reasons_success(self, mock_vc):
        """
        Executes query that udpates group error reasons
        """
        self.clock.advance(10.345)
        d = self.group.update_error_reasons(['r1', 'r2'])
        self.assertIsNone(self.successResultOf(d))  # update returns None
        expectedCql = (
            'INSERT INTO scaling_group("tenantId", "groupId", error_reasons) '
            'VALUES (:tenantId, :groupId, :reasons) USING TIMESTAMP :ts')
        expectedData = {"reasons": ['r1', 'r2'],
                        "groupId": '12345678g',
                        "tenantId": '11111', 'ts': 10345000}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    def test_update_error_reasons_no_group(self, mock_vc):
        """
        Raises NoSuchScalingGroupError if group is not found and does not
        execute update query
        """
        self.clock.advance(10.345)
        d = self.group.update_error_reasons(['r1', 'r2'])
        self.failureResultOf(d, NoSuchScalingGroupError)
        self.assertFalse(self.connection.execute.called)

    def test_view_config_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_config()
        self.failureResultOf(d, NoSuchScalingGroupError)
        expectedCql = (
            'SELECT group_config, created_at FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'AND deleting=false;')
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
            'SELECT launch_config, created_at FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'AND deleting=false;')
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
            'SELECT launch_config, created_at FROM scaling_group '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'AND deleting=false;')
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
        viewCql = ('SELECT launch_config, created_at '
                   'FROM scaling_group WHERE '
                   '"tenantId" = :tenantId AND "groupId" = :groupId '
                   'AND deleting=false;')
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
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed([{'id': 'w1'},
                                            {'id': 'w2'}]))
    def test_delete_policy_valid_policy(self, mock_webhooks, mock_get_policy):
        """
        When you delete a scaling policy, it checks if the policy exists and
        if it does, deletes the policy and all its associated webhooks.
        """
        d = self.group.delete_policy('3222')
        # delete returns None
        self.assertIsNone(self.successResultOf(d))
        mock_get_policy.assert_called_once_with('3222')
        mock_webhooks.assert_called_once_with('3222', 10000, None)

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

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    def test_update_config_bad(self, mock_vc):
        """
        Tests that you can't update non-existent scaling group
        """
        self.returns = []
        d = self.group.update_config({"b": "lah"})
        self.failureResultOf(d, NoSuchScalingGroupError)

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
        self.returns = [[{'group_config': '{}', 'created_at': 24}], []]
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

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed('watever'))
    def test_view_webhook(self, mock_vc):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [_cassandrify_data(
            [{'data': '{"name": "pokey"}', 'capability': '{"1": "h"}'}])]
        d = self.group.get_webhook("3444", "4555")
        r = self.successResultOf(d)
        mock_vc.assert_called_once_with()
        expectedCql = ('SELECT data, capability FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND "webhookId" = :webhookId;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g",
                        "policyId": "3444", "webhookId": "4555"}
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        self.assertEqual(
            r, {'name': 'pokey', 'capability': {"version": "1", "hash": "h"}})

    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_view_webhook_no_such_webhook(self, mock_vc):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        self.returns = [[]]
        d = self.group.get_webhook('3444', '4555')
        mock_vc.assert_called_once_with()
        self.failureResultOf(d, NoSuchWebhookError)
        self.flushLoggedErrors(NoSuchPolicyError)

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

    @mock.patch('otter.models.cass.CassScalingGroup.get_webhook')
    def test_delete_webhook(self, mock_gw):
        """
        Tests that you can delete a scaling policy webhook, and if successful
        return value is None
        """
        # return value for delete
        self.returns = [None]
        mock_gw.return_value = defer.succeed(
            {'data': '{}', 'capability': {"version": "1", "hash": "h"}})
        d = self.group.delete_webhook('3444', '4555')
        self.assertIsNone(self.successResultOf(d))  # delete returns None
        mock_gw.assert_called_once_with('3444', '4555')
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

        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

    @mock.patch('otter.models.cass.CassScalingGroup.get_webhook',
                return_value=defer.fail(NoSuchWebhookError(*range(4))))
    def test_delete_non_existant_webhooks(self, mock_gw):
        """
        If you try to delete a scaling policy webhook that doesn't exist,
        :class:`NoSuchWebhookError` is raised
        """
        self.returns = []
        d = self.group.delete_webhook('3444', '4555')
        self.failureResultOf(d, NoSuchWebhookError)
        mock_gw.assert_called_once_with('3444', '4555')
        self.flushLoggedErrors(NoSuchWebhookError)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_non_empty_scaling_non_deleting_group_fails(
            self, mock_view_state):
        """
        ``delete_group`` errbacks with :class:`GroupNotEmptyError` if scaling
        group state is not empty
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {'1': {}}, {}, None, {}, False,
            ScalingGroupStatus.ACTIVE))
        znodes = self.kz_client.nodes
        self.failureResultOf(self.group.delete_group(), GroupNotEmptyError)

        # nothing else called except view
        mock_view_state.assert_called_once_with(get_deleting=True)
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(GroupNotEmptyError)
        # locks znode is not deleted
        self.assertIs(self.kz_client.nodes, znodes)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks')
    def test_delete_non_empty_scaling_deleting_group_succeeds(
            self, mock_naive, mock_view_state):
        """
        ``delete_group`` succeeds even if the group is not empty if the group
        is in deleting state.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {'1': {}}, {}, None, {}, False,
            ScalingGroupStatus.DELETING))

        mock_naive.return_value = defer.succeed([])

        self.returns = [None]
        result = self.successResultOf(self.group.delete_group())
        self.assertIsNone(result)  # delete returns None

        mock_view_state.assert_called_once_with(get_deleting=True)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_all_webhooks')
    def test_delete_empty_scaling_group_with_policies(self, mock_naive,
                                                      mock_view_state):
        """
        ``delete_group`` deletes config, launch config, state, and the group's
        policies and webhooks if the scaling group is empty.
        """
        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False,
            ScalingGroupStatus.ACTIVE))
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

            'DELETE FROM servers_cache '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM scaling_group USING TIMESTAMP :ts '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

        self.assertFalse(self.lb.acquired)
        self.assertEqual(self.kz_client.nodes, {})

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
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False,
            ScalingGroupStatus.ACTIVE))
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

            'DELETE FROM servers_cache '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '

            'DELETE FROM scaling_group USING TIMESTAMP :ts '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.QUORUM)

        self.assertFalse(self.lb.acquired)
        self.assertEqual(self.kz_client.nodes, {})

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_not_acquired(self, mock_view_state):
        """
        If the lock is not acquired, do not delete the group.
        """
        self.acquire_call = (True, 10, Failure(ValueError('a')))

        mock_view_state.return_value = defer.succeed(GroupState(
            self.tenant_id, self.group_id, 'a', {}, {}, None, {}, False,
            ScalingGroupStatus.ACTIVE))

        d = self.group.delete_group()
        self.failureResultOf(d, ValueError)

        self.assertFalse(self.connection.execute.called)
        self.assertIs(self.lb.acquired, self.lb.NOT_STARTED)
        # locks znode is not deleted
        self.assertIn("/locks/" + self.group.uuid, self.kz_client.nodes)

    @mock.patch('otter.models.cass.CassScalingGroup.view_state')
    def test_delete_lock_with_log_category_locking(self, mock_view_state):
        """
        The lock is created with log with category as locking
        """
        log = self.group.log = mock.Mock()

        self.group.delete_group()

        log.bind.assert_called_once_with(
            system='CassScalingGroup.delete_group')
        log.bind().bind.assert_called_once_with(
            category='locking', lock_reason='delete_group')

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
            self.tenant_id, self.group_id, '', {}, {}, None, {}, False,
            ScalingGroupStatus.ACTIVE))
        mock_naive.return_value = defer.succeed([])
        called = []

        def not_empty_error(lockpath):
            called.append(0)
            self.assertEqual(lockpath, '/locks/' + self.group.uuid)
            return defer.fail(NotEmptyError((), {}))

        self.kz_client.delete = not_empty_error

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


class GetPolicyTests(CassScalingGroupTestCase):
    """
    Tests for :func:`CassScalingGroup.get_policy`
    """

    def setUp(self):
        """ Mock view_config """
        super(GetPolicyTests, self).setUp()
        self.mock_vc = patch(
            self, 'otter.models.cass.CassScalingGroup.view_config',
            return_value=defer.succeed({}))

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
            'created_at': 23,
            'deleting': False,
            'status': 'ACTIVE',
            'error_reasons': None,
            'suspended': None
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
                {'PT': 'R'}, False,
                ScalingGroupStatus.ACTIVE)
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
            'desired, created_at, status, error_reasons, deleting '
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
            self.mock_log)

    def test_different_status(self):
        """`status` is propagated to the manifest return value."""
        self.verified_view.return_value = defer.succeed(self.vv_return)

        self.vv_return['status'] = 'ERROR'
        self.manifest['state'].status = ScalingGroupStatus.ERROR

        self.assertEqual(
            self.validate_view_manifest_return_value(with_policies=False),
            self.manifest)

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

    def test_get_deleting_gets_deleting_group(self):
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
        self.manifest['state'].status = ScalingGroupStatus.DELETING
        self.assertEqual(resp, self.manifest)

    def test_nogrouperror_on_deleting_group(self):
        """
        Viewing manifest with `get_deleting=False` on a deleting group
        raises NoSuchScalingGroupError
        """
        self.vv_return['status'] = 'ERROR'
        self.vv_return['deleting'] = True
        self.verified_view.return_value = defer.succeed(self.vv_return)
        d = self.group.view_manifest(with_policies=False, get_deleting=False)
        self.failureResultOf(d, NoSuchScalingGroupError)

    def _check_with_deleting(self, status):
        self.verified_view.return_value = defer.succeed(self.vv_return)
        resp = self.validate_view_manifest_return_value(with_policies=False,
                                                        get_deleting=True)
        self.manifest['state'].status = status
        self.assertEqual(resp, self.manifest)

    def test_with_deleting_normal_group(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including status when group is not deleting
        """
        self.vv_return['status'] = 'ACTIVE'
        self._check_with_deleting(ScalingGroupStatus.ACTIVE)

    def test_with_deleting_none_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ACTIVE status when group is not deleting and status is None
        """
        self.vv_return['status'] = None
        self._check_with_deleting(ScalingGroupStatus.ACTIVE)

    def test_with_deleting_disabled_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ERROR status when group is not deleting and status is
        DISABLED
        """
        self.vv_return['status'] = 'DISABLED'
        self._check_with_deleting(ScalingGroupStatus.ERROR)

    def test_with_deleting_error_status(self):
        """
        Viewing manifest with `get_deleting=True` returns group manifest
        including ERROR status when group is not deleting and status is
        ERROR
        """
        self.vv_return['status'] = 'ERROR'
        self._check_with_deleting(ScalingGroupStatus.ERROR)

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
        self.store = CassScalingGroupCollection(None, None, 1)

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
            self.connection, self.clock, 1)

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
                                                     self.clock, 100)

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
            'deleting': False,
            'status': 'ACTIVE',
            'error_reasons': None,
            'suspended': None
        }

    @mock.patch('otter.models.cass.WeakLocks', return_value=2)
    def test_locks(self, mock_wl):
        """
        `CassScalingGroupCollection` keeps new WeakLocks object
        """
        collection = CassScalingGroupCollection(self.connection, self.clock, 1)
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
            'paused, desired, created_at, deleting, suspended) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at, false, false) '
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
            'desired, created_at, deleting, suspended) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at, false, false) '
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
            'desired, created_at, deleting, suspended) '
            'VALUES (:tenantId, :groupId, :group_config, :launch_config, '
            ':active, :pending, :policyTouched, :paused, :desired, '
            ':created_at, false, false) '
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
                       'WHERE "tenantId"=:tenantId AND deleting=false;')
        self.mock_key.return_value = '1111'

        d = self.collection.create_scaling_group(
            mock.Mock(), '1234', self.config, self.launch)
        self.assertTrue(isinstance(self.successResultOf(d), dict))

        self.assertEqual(len(self.connection.execute.mock_calls), 2)
        self.assertEqual(
            self.connection.execute.mock_calls[0],
            mock.call(expectedCQL, expectedData, ConsistencyLevel.ONE))

    def test_max_groups_overlimit(self):
        """
        test scaling group creation when at maxGroups limit
        """
        self.collection.max_groups = 1
        self.returns = [[{'count': 1}]]

        expectedData = {'tenantId': '1234'}
        expectedCQL = (
            'SELECT COUNT(*) FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false;')

        d = self.collection.create_scaling_group(
            mock.Mock(), '1234', self.config, self.launch)
        self.connection.execute.assert_called_once_with(
            expectedCQL, expectedData, ConsistencyLevel.ONE)

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
            'status, error_reasons '
            'FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false LIMIT :limit;')
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
                                     paused=False,
                                     status=ScalingGroupStatus.ACTIVE)
            return group_state

        self.assertEqual(r, [group_state_with_id("group0"),
                             group_state_with_id("group1")])

    def test_list_states_different_status(self):
        """The status from the response is honored."""
        self.returns = [[assoc(self.group, 'status', 'ERROR')]]

        expectedData = {'tenantId': '123', 'limit': 100}
        expectedCql = (
            'SELECT "tenantId", "groupId", group_config, active, pending, '
            '"groupTouched", "policyTouched", paused, desired, created_at, '
            'status, error_reasons '
            'FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false LIMIT :limit;')
        r = self.validate_list_states_return_value(self.mock_log, '123')
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.QUORUM)

        expected_group = GroupState(
            tenant_id='123',
            group_id='group',
            group_name='test',
            active={},
            pending={},
            group_touched='0001-01-01T00:00:00Z',
            policy_touched={},
            paused=False,
            status=ScalingGroupStatus.ERROR)
        self.assertEqual(r, [expected_group])

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
            'created_at, status, error_reasons FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false LIMIT :limit;')
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
            'status, error_reasons '
            'FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false '
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
            'status, error_reasons '
            'FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false AND '
            '"groupId" > :marker LIMIT :limit;')
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
            'status, error_reasons '
            'FROM scaling_group '
            'WHERE "tenantId"=:tenantId AND deleting=false LIMIT :limit;')
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
                                        paused=False,
                                        status=ScalingGroupStatus.ACTIVE)])
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
                                        paused=False,
                                        status=ScalingGroupStatus.ACTIVE)])

    def _extract_execute_query(self, call):
        args, _ = call
        query, params, c = args
        return query

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

    def test_webhook_info_by_hash(self):
        """
        `webhook_info_by_hash` gets the info from webhook_keys table
        """
        self.returns = [_cassandrify_data([
            {'tenantId': '123', 'groupId': 'group1', 'policyId': 'pol1'}]),
            _cassandrify_data([{'data': '{}'}])
        ]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId" '
                       'FROM webhook_keys '
                       'WHERE "webhookKey" = :webhookKey;')
        d = self.collection.webhook_info_by_hash(self.mock_log, 'x')
        r = self.successResultOf(d)
        self.assertEqual(r, ('123', 'group1', 'pol1'))
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

    def test_webhook_bad(self):
        """
        Test that a bad webhook will fail with UnrecognizedCapabilityError
        """
        self.returns = [[]]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId" '
                       'FROM webhook_keys '
                       'WHERE "webhookKey" = :webhookKey;')
        d = self.collection.webhook_info_by_hash(self.mock_log, 'x')
        self.failureResultOf(d, UnrecognizedCapabilityError)
        self.connection.execute.assert_called_once_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

    def test_get_counts(self):
        """
        Check get_count returns dictionary in proper format
        """
        self.returns = [
            [{'count': 101}],
            [{'count': 102}],
            [{'count': 100}],
        ]

        expectedData = {'tenantId': '123'}
        expectedResults = {
            "groups": 100,
            "policies": 101,
            "webhooks": 102
        }
        config_query = ('SELECT COUNT(*) FROM scaling_group '
                        'WHERE "tenantId"=:tenantId AND deleting=false;')
        policy_query = ('SELECT COUNT(*) FROM scaling_policies '
                        'WHERE "tenantId"=:tenantId ;')
        webhook_query = ('SELECT COUNT(*) FROM policy_webhooks '
                         'WHERE "tenantId"=:tenantId ;')

        calls = [
            mock.call(policy_query, expectedData, ConsistencyLevel.ONE),
            mock.call(webhook_query, expectedData, ConsistencyLevel.ONE),
            mock.call(config_query, expectedData, ConsistencyLevel.ONE)]

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
                                                     self.clock, 1)
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


class CassGroupServersCacheTests(SynchronousTestCase):
    """
    Tests for :class:`CassScalingGroupServersCache`
    """

    def setUp(self):
        self.tenant_id = 'tid'
        self.group_id = 'gid'
        self.params = {"tenantId": self.tenant_id, "groupId": self.group_id}
        self.clock = Clock()
        self.clock.advance(2.5)
        self.cache = CassScalingGroupServersCache(
            self.tenant_id, self.group_id, self.clock)
        self.dt = datetime(2010, 10, 20, 10, 0, 0)

    def _test_get_servers(self, only_as_active, query_result, exp_result):
        sequence = [
            (CQLQueryExecute(
                query=('SELECT server_blob, server_as_active, last_update '
                       'FROM servers_cache '
                       'WHERE "tenantId"=:tenantId AND "groupId"=:groupId '
                       'ORDER BY last_update DESC;'),
                params=self.params, consistency_level=ConsistencyLevel.QUORUM),
             lambda i: query_result)]
        self.assertEqual(
            perform_sequence(sequence, self.cache.get_servers(only_as_active),
                             test_dispatcher(sequence)),
            exp_result)

    def test_get_servers_empty(self):
        """
        `get_servers` returns ([], None) if cache is empty
        """
        self._test_get_servers(True, [], ([], None))
        self._test_get_servers(False, [], ([], None))

    def test_get_servers_all(self):
        """
        `get_servers` fetches all servers that have highest last_fetch
        time
        """
        self._test_get_servers(
            False,
            [{"server_blob": '{"a": "b"}', "last_update": self.dt,
              "server_as_active": False},
             {"server_blob": '{"d": "e"}', "last_update": self.dt,
              "server_as_active": False},
             {"server_blob": '{"2": "a"}', "last_update": self.dt,
              "server_as_active": True}],
            ([{"a": "b"}, {"d": "e"}, {"2": "a"}], self.dt))

    def test_get_servers_as_active(self):
        """
        `get_servers` fetches only AS active servers that have highest
        last_fetch time
        """
        self._test_get_servers(
            True,
            [{"server_blob": '{"a": "b"}', "last_update": self.dt,
              "server_as_active": True},
             {"server_blob": '{"d": "e"}', "last_update": self.dt,
              "server_as_active": False}],
            ([{"a": "b"}], self.dt))

    def test_get_servers_diff_last_update(self):
        """
        `get_servers` will return servers with only latest last_update time
        if there are multiple caches
        """
        dt_earlier = datetime(2010, 10, 15, 10, 0, 0)
        self._test_get_servers(
            False,
            [{"server_blob": '{"a": "b"}', "last_update": self.dt,
              "server_as_active": False},
             {"server_blob": '{"d": "e"}', "last_update": self.dt,
              "server_as_active": False},
             {"server_blob": '{"c": "f"}', "last_update": dt_earlier,
              "server_as_active": False}],
            ([{"a": "b"}, {"d": "e"}], self.dt))
        # Test with only_as_active as True
        self._test_get_servers(
            True,
            [{"server_blob": '{"a": "b"}', "last_update": self.dt,
              "server_as_active": False},
             {"server_blob": '{"d": "e"}', "last_update": self.dt,
              "server_as_active": True},
             {"server_blob": '{"c": "f"}', "last_update": dt_earlier,
              "server_as_active": True}],
            ([{"d": "e"}], self.dt))

    def _test_insert_servers(self, eff, ts=2500000):
        query = (
            'BEGIN BATCH USING TIMESTAMP {} '
            'INSERT INTO servers_cache ("tenantId", "groupId", last_update, '
            'server_id, server_blob, server_as_active) '
            'VALUES(:tenantId, :groupId, :last_update, :server_id0, '
            ':server_blob0, :server_as_active0); '
            'INSERT INTO servers_cache ("tenantId", "groupId", last_update, '
            'server_id, server_blob, server_as_active) '
            'VALUES(:tenantId, :groupId, :last_update, :server_id1, '
            ':server_blob1, :server_as_active1); APPLY BATCH;').format(ts)
        self.params.update(
            {"server_id0": "a", "server_blob0": '{"id": "a"}',
             "server_as_active0": True,
             "server_id1": "b", "server_blob1": '{"id": "b"}',
             "server_as_active1": False,
             "last_update": self.dt})
        self.assertEqual(eff, cql_eff(query, self.params))
        self.assertEqual(resolve_effect(eff, None), None)

    def test_insert_servers(self):
        """
        `insert_servers` issues query to insert server as json blobs
        """
        eff = self.cache.insert_servers(
            self.dt, [{"id": "a", "_is_as_active": True}, {"id": "b"}],
            clear_others=False)
        self._test_insert_servers(eff)

    def test_insert_servers_delete(self):
        """
        `insert_servers` deletes existing caches before inserting
        when clear_others=True
        """
        self.cache.delete_servers = lambda: Effect("delete")
        eff = self.cache.insert_servers(
            self.dt, [{"id": "a", "_is_as_active": True}, {"id": "b"}],
            clear_others=True)
        self.assertEqual(eff.intent, "delete")
        self.clock.advance(1)
        eff = resolve_effect(eff, None)
        self._test_insert_servers(eff, 3500000)

    def test_insert_empty(self):
        """
        `insert_servers` does nothing if called with empty servers list
        """
        self.assertEqual(
            self.cache.insert_servers(self.dt, [], clear_others=False),
            Effect(Constant(None)))

    def test_insert_empty_delete(self):
        """
        `insert_servers` deletes servers when clear_others=True and does
        nothing if passed list is empty
        """
        self.cache.delete_servers = lambda: Effect("delete")
        eff = self.cache.insert_servers(self.dt, [], clear_others=True)
        self.assertEqual(eff.intent, "delete")
        self.assertIsNone(resolve_effect(eff, None))

    def test_delete_servers(self):
        """
        `delete_servers` issues query to delete the whole cache
        """
        self.assertEqual(
            self.cache.delete_servers(),
            cql_eff(('DELETE FROM servers_cache USING TIMESTAMP :ts WHERE '
                     '"tenantId"=:tenantId AND "groupId"=:groupId'),
                    merge(self.params, {"ts": 2500000})))


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


class GetScalingGroupsTests(SynchronousTestCase):
    """Tests for ``get_all_valid_groups``."""

    @mock.patch("otter.models.cass.CassScalingGroupCollection"
                ".get_scaling_group_rows")
    def test_success(self, mock_gsgr):
        clock = Clock()
        client = mock.Mock(spec=CQLClient)
        collection = CassScalingGroupCollection(client, clock, 1)
        rows = [
            {'created_at': '0', 'desired': 'some', 'status': 'ACTIVE'},
            {'desired': 'some', 'status': 'ACTIVE'},  # no created_at
            {'created_at': '0', 'status': 'ACTIVE'},  # no desired
            {'created_at': '0', 'desired': 'some'},   # no status
            {'created_at': '0', 'desired': 'some', 'status': 'DISABLED'},
            {'created_at': '0', 'desired': 'some', 'deleting': 'True', },
            {'created_at': '0', 'desired': 'some', 'status': 'ERROR'}]
        rows = [assoc(row, "tenantId", "t1") for row in rows]
        mock_gsgr.return_value = defer.succeed(rows)
        results = self.successResultOf(collection.get_all_valid_groups())
        self.assertEqual(results, [rows[0], rows[3], rows[4], rows[6]])
        mock_gsgr.assert_called_once_with()


class GetScalingGroupRowsTests(SynchronousTestCase):
    """Tests for ``get_scaling_group_rows``."""

    def setUp(self):
        """Mock"""
        self.clock = Clock()
        self.client = mock.Mock(spec=CQLClient)
        self.collection = CassScalingGroupCollection(self.client,
                                                     self.clock, 1)
        self.exec_args = {}

        def _exec(query, params, c):
            return defer.succeed(self.exec_args[freeze((query, params))])

        self.client.execute.side_effect = _exec
        self.select = 'SELECT * FROM scaling_group '

    def _add_exec_args(self, query, params, ret):
        self.exec_args[freeze((query, params))] = ret

    def test_all_groups_less_than_batch(self):
        """
        Works when number of all groups of all tenants < batch size
        """
        groups = [{'tenantId': i, 'groupId': j,
                   'desired': 3, 'created_at': 'c'}
                  for i in range(2) for j in range(2)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = self.collection.get_scaling_group_rows(batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_gets_props(self):
        """
        If props arg is given then returns groups with only that property in it
        """
        groups = [{'tenantId': 1, 'groupId': 2, 'desired': 3,
                   'created_at': 'c', 'launch': 'l'},
                  {'tenantId': 1, 'groupId': 3, 'desired': 2,
                   'created_at': 'c', 'launch': 'b'}]
        self._add_exec_args(
            ('SELECT launch '
             'FROM scaling_group  LIMIT :limit;'),
            {'limit': 5}, groups)
        d = self.collection.get_scaling_group_rows(props=['launch'],
                                                   batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_last_tenant_has_less_groups(self):
        """
        Fetches initial batch, then gets all groups of last tenant
        in that batch and stops when there are no more tenants
        """
        groups = [{'tenantId': 1, 'groupId': i,
                   'desired': 3, 'created_at': 'c'}
                  for i in range(7)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups[:5])
        self._add_exec_args(
            self.select + ('WHERE "tenantId"=:tenantId AND '
                           '"groupId">:groupId LIMIT :limit;'),
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups[5:])
        self._add_exec_args(
            self.select + ('WHERE token("tenantId") > token(:tenantId)'
                           ' LIMIT :limit;'),
            {'limit': 5, 'tenantId': 1}, [])
        d = self.collection.get_scaling_group_rows(batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_many_tenants_having_more_than_batch_groups(self):
        """
        Gets all groups when there are many tenants each of them
        having groups > batch size
        """
        groups1 = [{'tenantId': 1, 'groupId': i,
                    'desired': 3, 'created_at': 'c'}
                   for i in range(7)]
        groups2 = [{'tenantId': 2, 'groupId': i,
                    'desired': 4, 'created_at': 'c'}
                   for i in range(9)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups1[:5])
        where_tenant = ('WHERE "tenantId"=:tenantId AND '
                        '"groupId">:groupId LIMIT :limit;')
        where_token = ('WHERE token("tenantId") > token(:tenantId) '
                       'LIMIT :limit;')
        self._add_exec_args(
            self.select + where_tenant,
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups1[5:])
        self._add_exec_args(
            self.select + where_token,
            {'limit': 5, 'tenantId': 1}, groups2[:5])
        self._add_exec_args(
            self.select + where_tenant,
            {'limit': 5, 'tenantId': 2, 'groupId': 4}, groups2[5:])
        self._add_exec_args(
            self.select + where_token,
            {'limit': 5, 'tenantId': 2}, [])
        d = self.collection.get_scaling_group_rows(batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups1 + groups2)
