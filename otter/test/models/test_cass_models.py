"""
Tests for :mod:`otter.models.mock`
"""
import json
import mock

from twisted.trial.unittest import TestCase

from otter.models.cass import (
    CassScalingGroup,
    CassScalingGroupCollection,
    CassBadDataError)

from otter.models.interface import (NoSuchScalingGroupError, NoSuchPolicyError,
                                    NoSuchWebhookError, UnrecognizedCapabilityError)

from otter.test.models.test_interface import (
    IScalingGroupStateProviderMixin,
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin)

from twisted.internet import defer
from silverberg.client import ConsistencyLevel


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
    results = []
    for data_dict in list_of_dicts:
        columns = []
        for key, value in data_dict.iteritems():
            columns.append({
                'timestamp': None,
                'name': key,
                'value': value,
                'ttl': None
            })
        results.append({'cols': columns, 'key': ''})
    return _de_identify(results)


class CassScalingGroupStateTestCase(IScalingGroupStateProviderMixin, TestCase):
    """
    Tests for :class:`CassScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.tenant_id = '11111'
        self.group_id = '12345789g'
        self.mock_log = mock.MagicMock()
        self.connection = mock.MagicMock(spec=['execute'])

        # config, launch config, etc. doesn't matter, only policies
        self.policies = [{
            "name": "set number of servers to 10",
            "steadyState": 10,
            "cooldown": 3
        }]
        self.state = CassScalingGroup(
            self.mock_log, self.tenant_id, self.group_id, self.connection)


class CassScalingGroupTestCase(IScalingGroupProviderMixin, TestCase):
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
        self.config = _de_identify({
            'name': '',
            'cooldown': 0,
            'minEntities': 0
        })
        # this is the config with all the default vals
        self.output_config = _de_identify({
            'name': '',
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
        self.group = CassScalingGroup(self.mock_log, self.tenant_id, '12345678g',
                                      self.connection)
        self.hashkey_patch = mock.patch(
            'otter.models.cass.generate_key_str')
        self.mock_key = self.hashkey_patch.start()
        self.mock_key.return_value = '12345678'
        self.addCleanup(self.hashkey_patch.stop)

        self.capability_patch = mock.patch(
            'otter.models.cass.generate_capability',
            return_value=('ver', 'hash'))
        self.mock_capability = self.capability_patch.start()
        self.addCleanup(self.capability_patch.stop)

        self.consistency_level_patch = mock.patch(
            'otter.models.cass.get_consistency_level',
            return_value=ConsistencyLevel.TWO)
        self.consistency_level_patch.start()
        self.addCleanup(self.consistency_level_patch.stop)

    def _test_view_things_errors(self, callback_to_test, *args, **kwargs):
        """
        Errors from cassandra in viewing one thing (not listing) or updating
        one thing (because it must first be viewed) cause
        :class:`CassBadDataErrors`
        """
        bads = (
            # no data
            None,
            # this should probably not happen
            [{}],
            # no results
            [{'cols': [{}]}],
            # no value
            [{'cols': [{'timestamp': None, 'name': 'data', 'ttl': None}],
              'key': ''}],
            # non json
            [{'cols': [{'timestamp': None, 'name': 'data',
                        'value': 'hi', 'ttl': None}],
              'key': ''}],
            [{'cols': [{'timestamp': None, 'name': 'data', 'value': '{ff}',
                       'ttl': None}],
             'key': ''}]

        )

        for bad in bads:
            self.returns = [bad]
            self.assert_deferred_failed(callback_to_test(*args, **kwargs),
                                        CassBadDataError)
            self.flushLoggedErrors(CassBadDataError)

    def test_view_config(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.view_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
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
            {'active': '{"F":"R"}', 'pending': '{"F":"R"}', 'groupTouched': '123',
             'policyTouched': '{"F":"R"}', 'paused': False}])

        self.returns = [cass_response]
        d = self.group.view_state()
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT active, pending, "groupTouched", "policyTouched", paused FROM '
                       'group_state WHERE "tenantId" = :tenantId AND "groupId" = :groupId AND '
                       'deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {'active': {'F': 'R'},
                             'groupTouched': '123',
                             'pending': {'F': 'R'},
                             'policyTouched': {'F': 'R'},
                             'paused': False})

    def test_view_config_bad_db_data(self):
        """
        Test what happens if you retrieve bad db config data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.view_config)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData,
                                             ConsistencyLevel.TWO))

    def test_view_config_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
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
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.view_config()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_view_launch(self):
        """
        Test that you can call view and receive a valid parsed response
        for the launch config
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_launch_bad_db_data(self):
        """
        Test what happens if you retrieve bad db launch data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.view_launch_config)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData,
                                             ConsistencyLevel.TWO))

    def test_view_launch_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
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
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.view_launch_config()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_update_config(self):
        """
        Test that you can update a config, and if its successful the return
        value is None
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [cass_response, None]
        d = self.group.update_config({"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
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
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [cass_response, None]
        d = self.group.update_launch_config({"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
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
                return_value=defer.fail(CassBadDataError("Cassandra failure")))
            self.assert_deferred_failed(callback(), CassBadDataError)

            # view is called
            self.group.view_config.assert_called_once_with()
            # but extra executes, to update, are not called
            self.assertFalse(self.connection.execute.called)
            self.flushLoggedErrors(CassBadDataError)

    def test_view_policy(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444")
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g", "policyId": "3444"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

    def test_view_policy_bad_db_data(self):
        """
        Test what happens if you retrieve bad db policy data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.get_policy, "3444")
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g", "policyId": "3444"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData,
                                             ConsistencyLevel.TWO))

    def test_view_policy_no_such_policy(self):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        cass_response = []
        self.returns = [cass_response]
        d = self.group.get_policy('3444')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
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
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [cass_response]
        d = self.group.get_policy("3444")
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_naive_list_policies_with_policies(self):
        """
        Naive list policies lists existing scaling policies
        """
        self.returns = [_cassandrify_data([
            {'policyId': 'policy1', 'data': '{}'},
            {'policyId': 'policy2', 'data': '{}'}])]

        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111'}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND deleted = False;')
        d = self.group._naive_list_policies()
        r = self.assert_deferred_succeeded(d)
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
        r = self.assert_deferred_succeeded(d)
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
        r = self.assert_deferred_succeeded(d)
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
        r = self.assert_deferred_succeeded(d)
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

    def test_list_policy_errors(self):
        """
        Errors from cassandra in listing policies cause :class:`CassBadDataErrors`
        """
        bads = (
            None,
            [{}],
            # no results
            [{'cols': [{}]}],
            # no value
            [{'cols': [{'timestamp': None, 'name': 'policyId', 'ttl': None},
                       {'timestamp': None, 'name': 'data', 'ttl': None}],
              'key': ''}],
            # missing one column
            [{'cols': [{'timestamp': None, 'name': 'policyId',
                        'value': 'policy1', 'ttl': None}],
              'key': ''}],
            [{'cols': [{'timestamp': None, 'name': 'data',
                        'value': '{}', 'ttl': None}],
              'key': ''}],
            # non json
            [{'cols': [{'timestamp': None, 'name': 'policyId',
                        'value': 'policy1', 'ttl': None},
                       {'timestamp': None, 'name': 'data',
                        'value': 'hi', 'ttl': None}],
              'key': ''}]
        )
        for bad in bads:
            self.returns = [bad]
            self.assert_deferred_failed(self.group.list_policies(),
                                        CassBadDataError)
            self.flushLoggedErrors(CassBadDataError)

    def test_list_policy_no_version(self):
        """
        When listing the policies, any version information is removed from the
        final output
        """
        cass_response = [
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group1', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{"_ver": 5}', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group3', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{"_ver": 2}', 'ttl': None}], 'key': ''}]
        self.returns = [cass_response]
        d = self.group.list_policies()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {'group1': {}, 'group3': {}})

    def test_add_scaling_policy(self):
        """
        Test that you can add a scaling policy, and what is returned is a
        dictionary of the ids to the scaling policies
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [cass_response, None]
        d = self.group.create_policies([{"b": "lah"}])
        result = self.assert_deferred_succeeded(d)
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
                       'data, deleted) VALUES (:tenantId, :groupId, :policy0Id, :policy0, False) '
                       'APPLY BATCH;')
        expectedData = {"policy0": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "policy0Id": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

        self.assertEqual(result, {self.mock_key.return_value: {'b': 'lah'}})

    def test_add_first_checks_view_config(self):
        """
        Before a policy is added, `view_config` is first called to determine
        that there is such a scaling group
        """
        self.group.view_config = mock.MagicMock(return_value=defer.succeed({}))
        self.returns = [None]
        d = self.group.create_policies([{"b": "lah"}])
        self.assert_deferred_succeeded(d)
        self.group.view_config.assert_called_once_with()

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup.list_webhooks')
    def test_naive_delete_policy_no_webhooks(self, mock_list_webhooks,
                                             mock_naive, mock_get_policy):
        """
        When you delete a scaling policy, the policy is deleted but if there are
        no webhooks no call to delete its webhooks is made.

        No call to verify if the policy exists is made.  For
        listing the webhooks, ``_naive_list_webhooks`` is called, not
        ``list_webhooks`.

        ``naive_delete_policy`` should also use the consistency level provided

        There is no assertion about the return value, because that doesn't
        really matter.
        """
        self.returns = [None]
        self.group._naive_delete_policy('3222', ConsistencyLevel.TWO)
        # make sure that delete policy execution happend
        self.connection.execute.assert_called_once_with(
            ('BEGIN BATCH UPDATE scaling_policies SET deleted=True WHERE '
             '"tenantId" = :tenantId AND "groupId" = :groupId AND "policyId" = :policyId '
             'APPLY BATCH;'),
            {"tenantId": "11111", "groupId": "12345678g", "policyId": "3222"},
            ConsistencyLevel.TWO)

        self.assertEqual(len(mock_get_policy.mock_calls), 0)
        self.assertEqual(len(mock_list_webhooks.mock_calls), 0)
        mock_naive.assert_called_with('3222')

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_webhooks',
                return_value=defer.succeed({'webhook1': {}, 'webhook2': {}}))
    @mock.patch('otter.models.cass.CassScalingGroup.list_webhooks')
    def test_naive_delete_policy_some_webhooks(self, mock_list_webhooks,
                                               mock_naive, mock_get_policy):
        """
        When you delete a scaling policy with webhooks, the policy itself and
        its webhooks are deleted.

        No call to verify if the policy exists is made.  For
        listing the webhooks, ``_naive_list_webhooks`` is called, not
        ``list_webhooks`.

        ``naive_delete_policy`` should also use the consistency level provided

        There is no assertion about the return value, because that doesn't
        really matter.
        """
        self.returns = [None, None]
        self.group._naive_delete_policy('3222', ConsistencyLevel.TWO)
        # make sure that delete policy execution happend
        self.connection.execute.assert_any_call(
            ('BEGIN BATCH UPDATE policy_webhooks SET deleted=True WHERE '
             '"tenantId" = :tenantId AND "groupId" = :groupId AND '
             '"policyId" = :policyId AND "webhookId" = :webhookId0 '
             'UPDATE policy_webhooks SET deleted=True WHERE '
             '"tenantId" = :tenantId AND "groupId" = :groupId AND '
             '"policyId" = :policyId AND "webhookId" = :webhookId1 '
             'APPLY BATCH;'),
            {"tenantId": "11111", "groupId": "12345678g",
             "policyId": "3222", "webhookId0": "webhook1",
             "webhookId1": "webhook2"},
            ConsistencyLevel.TWO)

        # =/  has_calls doesn't mean "has only these calls"
        self.assertEqual(len(self.connection.execute.mock_calls), 2)

        self.assertEqual(len(mock_get_policy.mock_calls), 0)
        self.assertEqual(len(mock_list_webhooks.mock_calls), 0)
        mock_naive.assert_called_with('3222')

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_delete_policy',
                return_value=defer.succeed(None))
    def test_delete_policy_valid_policy(self, mock_naive, mock_get_policy):
        """
        When you delete a scaling policy, it checks if the policy exists and
        if it does, calls _naive_delete_policy and if it succeeds, returns None
        """
        d = self.group.delete_policy('3222')
        # delete returns None
        self.assertIsNone(self.assert_deferred_succeeded(d))
        mock_get_policy.assert_called_once_with('3222')
        mock_naive.assert_called_once_with('3222', ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup.get_policy',
                return_value=defer.fail(NoSuchPolicyError('t', 'g', 'p')))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_delete_policy',
                return_value=defer.succeed(None))
    def test_delete_policy_invalid_policy(self, mock_naive, mock_get_policy):
        """
        When you delete a scaling policy that doesn't exist, a
        :class:`NoSuchPolicyError` is raised
        """
        d = self.group.delete_policy('3222')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        mock_get_policy.assert_called_once_with('3222')
        self.assertEqual(len(mock_naive.mock_calls), 0)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_scaling_policy(self):
        """
        Test that you can update a scaling policy, and if successful it returns
        None
        """
        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [cass_response, None]
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
            'VALUES (:tenantId, :groupId, :policyId, :policy) APPLY BATCH;')
        expectedData = {"policy": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.TWO)

    def test_update_scaling_policy_bad(self):
        """
        Tests that if you try to update a scaling policy that doesn't exist, the right thing happens
        """
        self.returns = [[], None]
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"groupId": '12345678g',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_update_bad(self):
        """
        Tests that you can't just create a scaling group by sending
        an update to a nonexistant group
        """
        self.returns = [[], None]
        d = self.group.update_config({"b": "lah"})
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
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
            return_value=defer.fail(CassBadDataError("Cassandra failure")))
        self.assert_deferred_failed(self.group.update_policy('1', {'b': 'lah'}),
                                    CassBadDataError)

        # view is called
        self.group.get_policy.assert_called_once_with('1')
        # but extra executes, to update, are not called
        self.assertFalse(self.connection.execute.called)
        self.flushLoggedErrors(CassBadDataError)

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
            'data, capability, "webhookKey", deleted) VALUES (:tenantId, :groupId, :policyId, '
            ':webhook0Id, :webhook0, :webhook0Capability, :webhook0Key, False) '
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", "webhookId", '
            'data, capability, "webhookKey", deleted) VALUES (:tenantId, :groupId, :policyId, '
            ':webhook1Id, :webhook1, :webhook1Capability, :webhook1Key, False) '
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
        expectedCql = ('SELECT "webhookId", data, capability FROM policy_webhooks '
                       'WHERE "tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND deleted = False;')
        r = self.assert_deferred_succeeded(
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
        r = self.assert_deferred_succeeded(
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
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data, capability FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND "webhookId" = :webhookId AND '
                       'deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g",
                        "policyId": "3444", "webhookId": "4555"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(
            r, {'name': 'pokey', 'capability': {"version": "1", "hash": "h"}})

    def test_view_webhook_bad_db_data(self):
        """
        Test what happens if you retrieve bad db policy data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.get_webhook, "3444", "4555")

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
        r = self.assert_deferred_succeeded(d)
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
        self.assertIsNone(self.assert_deferred_succeeded(d))

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
        self.assertIsNone(self.assert_deferred_succeeded(d))

        expected_webhook_data = {
            'name': 'newname',
            'metadata': {}
        }
        self.assertEqual(self.connection.execute.call_args[0][1]['data'],
                         expected_webhook_data)

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
        self.assertIsNone(self.assert_deferred_succeeded(d))  # delete returns None
        expectedCql = ('UPDATE policy_webhooks SET deleted=True WHERE '
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
        self.hashkey_patch = mock.patch(
            'otter.models.cass.generate_key_str')
        self.mock_key = self.hashkey_patch.start()
        self.addCleanup(self.hashkey_patch.stop)

        self.consistency_level_patch = mock.patch(
            'otter.models.cass.get_consistency_level',
            return_value=ConsistencyLevel.TWO)
        self.consistency_level_patch.start()
        self.addCleanup(self.consistency_level_patch.stop)

    def test_create(self):
        """
        Test that you can create a group, and if successful the group ID is
        returned
        """
        expectedData = {
            'scaling': '{"_ver": 1}',
            'launch': '{"_ver": 1}',
            'groupId': '12345678',
            'tenantId': '123'}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, '
                       ':scaling, False) INSERT INTO launch_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, :launch, False) '
                       'APPLY BATCH;')
        self.mock_key.return_value = '12345678'
        d = self.collection.create_scaling_group(self.mock_log, '123', {}, {})
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_create_policy(self):
        """
        Test that you can create a scaling group with a single policy, and if
        successful the group ID is returned
        """
        expectedData = {
            'scaling': '{"_ver": 1}',
            'launch': '{"_ver": 1}',
            'groupId': '12345678',
            'tenantId': '123',
            'policy0Id': '12345678',
            'policy0': '{"_ver": 1}'}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, '
                       ':scaling, False) INSERT INTO launch_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, :launch, False) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, deleted) '
                       'VALUES (:tenantId, :groupId, :policy0Id, :policy0, False) '
                       'APPLY BATCH;')
        self.mock_key.return_value = '12345678'
        d = self.collection.create_scaling_group(self.mock_log, '123', {}, {}, [{}])
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_create_policy_multiple(self):
        """
        Test that you can create a scaling group with multiple policies, and if
        successful the group ID is returned
        """
        expectedData = {
            'scaling': '{"_ver": 1}',
            'launch': '{"_ver": 1}',
            'groupId': '12345678',
            'tenantId': '123',
            'policy0Id': '12345678',
            'policy0': '{"_ver": 1}',
            'policy1Id': '12345678',
            'policy1': '{"_ver": 1}'}
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, '
                       ':scaling, False) INSERT INTO launch_config("tenantId", '
                       '"groupId", data, deleted) VALUES (:tenantId, :groupId, :launch, False) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, deleted) '
                       'VALUES (:tenantId, :groupId, :policy0Id, :policy0, False) '
                       'INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data, deleted) '
                       'VALUES (:tenantId, :groupId, :policy1Id, :policy1, False) '
                       'APPLY BATCH;')
        self.mock_key.return_value = '12345678'
        d = self.collection.create_scaling_group(self.mock_log, '123', {}, {}, [{}, {}])
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list(self):
        """
        Test that you can list a bunch of configs.
        """
        self.returns = [[
            {'cols': [{'timestamp': None, 'name': 'groupId',
                       'value': 'group1', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'groupId',
                       'value': 'group3', 'ttl': None}], 'key': ''}]]

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "groupId" FROM scaling_config WHERE "tenantId" = :tenantId '
                       'AND deleted = False;')
        d = self.collection.list_scaling_groups(self.mock_log, '123')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 2)
        for row in r:
            self.assertEqual(row.tenant_id, '123')
        self.assertEqual(r[0].uuid, 'group1')
        self.assertEqual(r[1].uuid, 'group3')
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_empty(self):
        """
        Test that you can list a bunch of configs.
        """
        self.returns = [[]]

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "groupId" FROM scaling_config WHERE "tenantId" = :tenantId '
                       'AND deleted = False;')
        d = self.collection.list_scaling_groups(self.mock_log, '123')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 0)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_errors(self):
        """
        Errors from cassandra in listing groups cause :class:`CassBadDataErrors`
        """
        bads = (
            None,
            [{}],
            # no results
            [{'cols': [{}]}],
            # no value
            [{'cols': [{'timestamp': None, 'name': 'groupId', 'ttl': None}],
              'key': ''}],
            # wrong column
            [{'cols': [{'timestamp': None, 'name': 'data',
                        'value': '{}', 'ttl': None}],
              'key': ''}]
        )
        for bad in bads:
            self.returns = [bad]
            self.assert_deferred_failed(self.collection.list_scaling_groups(self.mock_log, '123'),
                                        CassBadDataError)
            self.flushLoggedErrors(CassBadDataError)

    def test_get_scaling_group(self):
        """
        Tests that you can get a scaling group
        (note that it doesn't request the database)
        """
        g = self.collection.get_scaling_group(self.mock_log, '123', '12345678')
        self.assertTrue(isinstance(g, CassScalingGroup))
        self.assertEqual(g.uuid, '12345678')
        self.assertEqual(g.tenant_id, '123')

    @mock.patch('otter.models.cass.CassScalingGroup._naive_delete_policy',
                return_value=defer.succeed(None))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies')
    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.fail(NoSuchScalingGroupError('t', 'g')))
    def test_delete_non_existant_scaling_group_fails(self, mock_view_config,
                                                     mock_naive_list_policy,
                                                     mock_naive_del_policy):
        """
        If the scaling group doesn't exist, :class:`NoSuchScalingGroup` is
        raised
        """
        self.assert_deferred_failed(
            self.collection.delete_scaling_group(self.mock_log, '123', 'group1'),
            NoSuchScalingGroupError)

        # only called once to view
        mock_view_config.assert_called_once_with()

        # nothing else called
        self.assertEqual(len(mock_naive_list_policy.mock_calls), 0)
        self.assertEqual(len(mock_naive_del_policy.mock_calls), 0)

        self.flushLoggedErrors(NoSuchScalingGroupError)

    @mock.patch('otter.models.cass.CassScalingGroup._naive_delete_policy',
                return_value=defer.succeed(None))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed({'policy1': {}, 'policy2': {}}))
    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup.list_policies')
    @mock.patch('otter.models.cass.CassScalingGroup.delete_policy')
    def test_delete_existing_scaling_group_with_policies(self, mock_del, mock_list,
                                                         mock_view_config,
                                                         mock_naive_list_policy,
                                                         mock_naive_del_policy):
        """
        If the scaling group exists, deletes scaling group and all of its
        policies and webhooks.  Use naive calls all the way down.
        """
        # we mock out delete policy, since that is already tested separately

        self.returns = [None]
        result = self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.mock_log, '123', 'group1'))
        self.assertIsNone(result)  # delete returns None

        # view config called to verify group exists
        mock_view_config.assert_called_once_with()

        # naive_list_policies called before naive_delete_policy called
        mock_naive_list_policy.assert_called_once_with()
        mock_naive_del_policy.assert_has_calls([
            mock.call('policy1', ConsistencyLevel.TWO),
            mock.call('policy2', ConsistencyLevel.TWO)], any_order=True)

        # the real delete and list policies are not called ever
        self.assertEqual(len(mock_del.mock_calls), 0)
        self.assertEqual(len(mock_list.mock_calls), 0)

        # delete configs happens
        expected_data = {'tenantId': '123',
                         'groupId': 'group1'}
        expected_cql = (
            'BEGIN BATCH '
            'UPDATE scaling_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'UPDATE launch_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')
        self.connection.execute.assert_called_once_with(
            expected_cql, expected_data, ConsistencyLevel.TWO)

    @mock.patch('otter.models.cass.CassScalingGroup._naive_delete_policy',
                return_value=defer.succeed(None))
    @mock.patch('otter.models.cass.CassScalingGroup._naive_list_policies',
                return_value=defer.succeed({}))
    @mock.patch('otter.models.cass.CassScalingGroup.view_config',
                return_value=defer.succeed({}))
    def test_delete_existing_scaling_group_with_no_policies(self,
                                                            mock_view_config,
                                                            mock_naive_list_policy,
                                                            mock_naive_del_policy):
        """
        If the scaling group exists but no scaling policies exist, deletes
        only the configs.  ``_naive_delete_policy`` is not called.
        """
        self.returns = [None]
        result = self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.mock_log, '123', 'group1'))
        self.assertIsNone(result)  # delete returns None

        # view config called to verify group exists
        mock_view_config.assert_called_once_with()

        # naive_list_policies called before delete policy called
        mock_naive_list_policy.assert_called_once_with()
        self.assertEqual(len(mock_naive_del_policy.mock_calls), 0)

    def test_webhook_hash(self):
        """
        Test that you can execute a webhook hash
        """
        self.returns = [_cassandrify_data([
            {'tenantId': '123', 'groupId': 'group1', 'policyId': 'pol1', 'deleted': False}]),
            _cassandrify_data([{'data': '{}'}])
        ]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId", deleted FROM policy_webhooks WHERE '
                       '"webhookKey" = :webhookKey;')
        d = self.collection.execute_webhook_hash(self.mock_log, 'x')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, None)
        self.connection.execute.assert_called_any(expectedCql,
                                                  expectedData,
                                                  ConsistencyLevel.TWO)

        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "123", "groupId": "group1", "policyId": "pol1"}
        self.connection.execute.assert_called_any(expectedCql,
                                                  expectedData,
                                                  ConsistencyLevel.TWO)

    def test_webhook_bad(self):
        """
        Test that a bad webhook will fail predictably
        """
        self.returns = [None]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId", deleted FROM policy_webhooks WHERE '
                       '"webhookKey" = :webhookKey;')
        d = self.collection.execute_webhook_hash(self.mock_log, 'x')
        self.assert_deferred_failed(d, UnrecognizedCapabilityError)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_webhook_deleted(self):
        """
        Test that deletion works
        """
        self.returns = [_cassandrify_data([
            {'tenantId': '123', 'groupId': 'group1', 'policyId': 'pol1', 'deleted': True}])
        ]
        expectedData = {'webhookKey': 'x'}
        expectedCql = ('SELECT "tenantId", "groupId", "policyId", deleted FROM policy_webhooks WHERE '
                       '"webhookKey" = :webhookKey;')
        d = self.collection.execute_webhook_hash(self.mock_log, 'x')
        self.assert_deferred_failed(d, UnrecognizedCapabilityError)

        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
