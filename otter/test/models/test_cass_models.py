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


class CassScalingGroupTestCase(IScalingGroupProviderMixin, TestCase):
    """
    Tests for :class:`MockScalingGroup`
    """

    def setUp(self):
        """
        Create a mock group
        """
        self.connection = mock.MagicMock()

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

    def test_list_policy(self):
        """
        Test that you can list a bunch of scaling policies.
        """
        cass_response = [
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group1', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{}', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group3', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{}', 'ttl': None}], 'key': ''}]
        self.returns = [cass_response]
        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111'}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND deleted = False;')
        d = self.group.list_policies()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 2)
        self.assertEqual(r, {'group1': {}, 'group3': {}})

        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_policy_empty_list(self):
        """
        If the group exists but there are no policies, `list_policies` returns
        an empty list
        """
        def execute_respond(cql, cqlargs, *other_args, **kwargs):
            if 'scaling_config' in cql:  # view config - seeing if it's there
                return defer.succeed(_de_identify([
                    {'cols': [{'timestamp': None,
                               'name': 'data',
                               'value': '{"_ver": 5}',
                               'ttl': None}],
                     'key': ''}]))
            else:
                return defer.succeed(_de_identify([]))
        self.connection.execute.side_effect = execute_respond

        result = self.assert_deferred_succeeded(self.group.list_policies())
        self.assertEqual(result, {})

    def test_list_policy_invalid_group(self):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingGroupError`
        """
        # no scaling policies, and view config is empty too
        self.returns = [[], []]
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

    def test_delete_policy(self):
        """
        Tests that you can delete a scaling policy, and if successful return
        value is None
        """
        view_policy = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [view_policy, None]
        d = self.group.delete_policy('3222')
        self.assertIsNone(self.assert_deferred_succeeded(d))  # delete returns None
        expectedCql = ('BEGIN BATCH UPDATE scaling_policies SET deleted=True WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND "policyId" = :policyId '
                       'APPLY BATCH;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g", "policyId": "3222"}

        self.assertEqual(len(self.connection.execute.mock_calls), 2)  # view, delete
        self.connection.execute.assert_called_with(expectedCql,
                                                   expectedData,
                                                   ConsistencyLevel.TWO)

    def test_delete_non_existant_policy(self):
        """
        If you try to delete a scaling policy that doesn't exist,
        :class:`NoSuchPolicyError` is raised
        """
        self.returns = [[], None]
        d = self.group.delete_policy('3222')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        self.assertEqual(len(self.connection.execute.mock_calls), 1)  # only view
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

    def test_add_webhooks_valid_policy(self):
        """
        When adding one or more webhooks is successful, what is returned is a
        dictionary of the webhook ids to the webhooks, which include capability
        info and metadata.
        """
        mock_ids = ['100001', '100002']

        def _return_uuid(*args, **kwargs):
            return mock_ids.pop(0)

        self.mock_key.side_effect = _return_uuid

        cass_response = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [cass_response, None]
        d = self.group.create_webhooks('23456789', [{}, {'metadata': 'who'}])

        expected_results = {
            '100001': {'metadata': {}},
            '100002': {'metadata': 'who'}
        }
        capability = {'capability': {"hash": 'hash', "version": 'ver'}}
        for value in expected_results.values():
            value.update(capability)

        result = self.assert_deferred_succeeded(d)
        self.assertEqual(result, dict(expected_results))

        expected_cql = (
            'BEGIN BATCH '
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", "webhookId", '
            'data, "webhookKey", deleted) VALUES (:tenantId, :groupId, :policyId, '
            ':webhook0Id, :webhook0, :webhook0Key, False) '
            'INSERT INTO policy_webhooks("tenantId", "groupId", "policyId", "webhookId", '
            'data, "webhookKey", deleted) VALUES (:tenantId, :groupId, :policyId, '
            ':webhook1Id, :webhook1, :webhook1Key, False) '
            'APPLY BATCH;')
        self.connection.execute.assert_called_with(
            expected_cql, mock.ANY, ConsistencyLevel.TWO)

        version = {'_ver': 1}
        for value in expected_results.values():
            value.update(version)

        # have to pull out the serialized JSON, load it as an object, and then
        # compare
        cql_params = self.connection.execute.call_args[0][1]
        expected_params = {
            "tenantId": '11111',
            "groupId": '12345678g',
            "policyId": '23456789',
            'webhook0Id': '100001',
            "webhook0Key": "hash",
            'webhook1Id': '100002',
            "webhook1Key": "hash"
        }
        for key, val in expected_params.iteritems():
            self.assertEqual(cql_params[key], val)

        self.assertEqual(len(cql_params), len(expected_params) + 2)
        self.assertEqual(json.loads(cql_params['webhook0']),
                         expected_results['100001'])
        self.assertEqual(json.loads(cql_params['webhook1']),
                         expected_results['100002'])

    def test_add_webhooks_invalid_policy(self):
        """
        Can't add webhooks to an invalid policy.
        """
        self.returns = [[], None]
        d = self.group.create_webhooks('23456789', [{}, {'metadata': 'who'}])
        self.assert_deferred_failed(d, NoSuchPolicyError)

    def test_list_webhooks_valid_policy(self):
        """
        Listing a valid policy produces a valid dictionary as per
        :data:`otter.json_schema.model_schemas.webhook_list`
        """
        data = json.dumps(self.sample_webhook_data)
        self.returns = [_cassandrify_data([
            {'webhookId': 'webhook1', 'data': data},
            {'webhookId': 'webhook2', 'data': data}
        ])]

        expectedData = {"groupId": '12345678g',
                        "tenantId": '11111',
                        "policyId": '23456789'}
        expectedCql = ('SELECT "webhookId", data FROM policy_webhooks WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                       '"policyId" = :policyId AND deleted = False;')
        r = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(r, {'webhook1': self.sample_webhook_data,
                             'webhook2': self.sample_webhook_data})
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)

    def test_list_webhooks_empty_list(self):
        """
        If the policy exists but there are no webhooks, `list_webhooks` returns
        an empty list
        """
        def execute_respond(cql, cqlargs, *other_args, **kwargs):
            if 'scaling_policies' in cql:  # view policy - seeing if it's there
                return defer.succeed(_cassandrify_data([{'data': '{}'}]))
            else:
                return defer.succeed(_de_identify([]))
        self.connection.execute.side_effect = execute_respond

        result = self.validate_list_webhooks_return_value('23456789')
        self.assertEqual(result, {})

    def test_list_webhooks_invalid_policy(self):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingPolicy`
        """
        # no scaling policies, and view config is empty too
        self.returns = [[], []]
        self.assert_deferred_failed(self.group.list_webhooks('23456789'),
                                    NoSuchPolicyError)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_view_webhook(self):
        """
        Test that you can call view and receive a valid parsed response
        """
        self.returns = [_cassandrify_data([{'data': '{}'}])]
        d = self.group.get_webhook("3444", "4555")
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM policy_webhooks WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND '
                       '"webhookId" = :webhookId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678g",
                        "policyId": "3444", "webhookId": "4555"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.TWO)
        self.assertEqual(r, {})

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

    def test_delete_webhook(self):
        """
        Tests that you can delete a scaling policy webhook, and if successful
        return value is None
        """
        # return values for get webhook and then delete
        self.returns = [_cassandrify_data([{'data': '{}'}]), None]
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
        self.connection = mock.MagicMock()

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

    def test_delete_non_existant_scaling_group_fails(self):
        """
        If the scaling group doesn't exist, :class:`NoSuchScalingGroup` is
        raised
        """
        self.returns = [[], None]  # view returns an empty list

        self.assert_deferred_failed(
            self.collection.delete_scaling_group(self.mock_log, '123', 'group1'),
            NoSuchScalingGroupError)
        self.flushLoggedErrors(NoSuchScalingGroupError)
        # only called once to view
        self.assertEqual(len(self.connection.execute.mock_calls), 1)

    def test_delete_existing_scaling_group(self):
        """
        If the scaling group exists, deletes scaling group
        """
        def execute_respond(query, *args, **kwargs):
            if query.lower().startswith("select"):
                # this query is to get the ids of all the policies.  make
                # sure there are some
                if "policyId" in query:
                    return defer.succeed(_de_identify([{
                        'cols': [{'timestamp': None, 'name': 'policyId',
                                  'value': 'pol1', 'ttl': None},
                                 {'timestamp': None, 'name': 'data',
                                  'value': '{"_ver": 5}', 'ttl': None}],
                        'key': ''}]))
                # nope, this query is to see if the group exists.
                # make sure it does
                return defer.succeed(_de_identify([{
                    'cols': [{'timestamp': None, 'name': 'data',
                              'value': '{}', 'ttl': None}],
                    'key': ''}]))

            # the rest of the queries are updates
            return defer.succeed(None)

        self.connection.execute.side_effect = execute_respond

        result = self.assert_deferred_succeeded(
            self.collection.delete_scaling_group(self.mock_log, '123', 'group1'))
        self.assertIsNone(result)  # delete returns None
        # called four times - once to view config, once to delete configs,
        # once to view policies, and once to delete policies
        self.assertEqual(len(self.connection.execute.mock_calls), 4)

        # delete configs
        expected_data = {'tenantId': '123',
                         'groupId': 'group1'}
        expected_cql = (
            'BEGIN BATCH '
            'UPDATE scaling_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'UPDATE launch_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')
        self.connection.execute.assert_called_any(expected_cql, expected_data,
                                                  ConsistencyLevel.TWO)

        # delete policies
        expected_data = {'tenantId': '123',
                         'groupId': 'group1',
                         'policyId0': 'pol1'}
        expected_cql = (
            'BEGIN BATCH '
            'UPDATE scaling_policies SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'AND "policyId" = :policyId0 '
            'APPLY BATCH;')
        self.connection.execute.assert_called_any(expected_cql, expected_data,
                                                  ConsistencyLevel.TWO)

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
