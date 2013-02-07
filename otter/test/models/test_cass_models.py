"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.models.cass import (
    CassScalingGroup,
    CassScalingGroupCollection,
    CassBadDataError)

from otter.models.interface import NoSuchScalingGroupError, NoSuchPolicyError

from otter.test.models.test_interface import (
    IScalingGroupProviderMixin,
    IScalingGroupCollectionProviderMixin)

from twisted.internet import defer
from silverberg.client import ConsistencyLevel


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
            result = self.returns.pop(0)
            if isinstance(result, Exception):
                return defer.fail(result)
            return defer.succeed(result)

        self.connection.execute.side_effect = _responses

        self.tenant_id = '11111'
        self.config = {
            'name': '',
            'cooldown': 0,
            'minEntities': 0
        }
        # this is the config with all the default vals
        self.output_config = {
            'name': '',
            'cooldown': 0,
            'minEntities': 0,
            'maxEntities': None,
            'metadata': {}
        }
        self.launch_config = {
            "type": "launch_server",
            "args": {"server": {"these are": "some args"}}
        }
        self.policies = []
        self.group = CassScalingGroup(self.tenant_id, '12345678',
                                      self.connection)
        self.hashkey_patch = mock.patch(
            'otter.models.cass.generate_key_str')
        self.mock_key = self.hashkey_patch.start()
        self.mock_key.return_value = '12345678'
        self.addCleanup(self.hashkey_patch.stop)

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
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.view_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.assertEqual(r, {})

    def test_view_config_bad_db_data(self):
        """
        Test what happens if you retrieve bad db config data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.view_config)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData))

    def test_view_config_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        mock = []
        self.returns = [mock]
        d = self.group.view_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM scaling_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_view_config_no_version(self):
        """
        When viewing the config, any version information is removed from the
        final output
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.view_config()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_view_launch(self):
        """
        Test that you can call view and receive a valid parsed response
        for the launch config
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.view_launch_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.assertEqual(r, {})

    def test_view_launch_bad_db_data(self):
        """
        Test what happens if you retrieve bad db launch data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.view_launch_config)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData))

    def test_view_launch_no_such_group(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        mock = []
        self.returns = [mock]
        d = self.group.view_launch_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = ('SELECT data FROM launch_config WHERE '
                       '"tenantId" = :tenantId AND "groupId" = :groupId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def test_view_launch_no_version(self):
        """
        When viewing the launch config, any version information is removed from
        the final output
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.view_launch_config()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_update_config(self):
        """
        Test that you can update a config, and if its successful the return
        value is None
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.update_config({"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_config("tenantId", "groupId", data) VALUES '
                       '(:tenantId, :groupId, :scaling) APPLY BATCH;')
        expectedData = {"scaling": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

    def test_update_launch(self):
        """
        Test that you can update a launch config, and if successful the return
        value is None
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.update_launch_config({"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
        expectedCql = ('BEGIN BATCH INSERT INTO launch_config("tenantId", "groupId", data) VALUES '
                       '(:tenantId, :groupId, :launch) APPLY BATCH;')
        expectedData = {"launch": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

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
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.get_policy("3444")
        r = self.assert_deferred_succeeded(d)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678", "policyId": "3444"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.assertEqual(r, {})

    def test_view_policy_bad_db_data(self):
        """
        Test what happens if you retrieve bad db policy data, including None, rows
        without keys, or bad JSON data (e.g. database corruption)
        """
        self._test_view_things_errors(self.group.get_policy, "3444")
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678", "policyId": "3444"}
        for call in self.connection.execute.call_args_list:
            self.assertEqual(call, mock.call(expectedCql, expectedData))

    def test_view_policy_no_such_policy(self):
        """
        Tests what happens if you try to view a policy that doesn't exist.
        """
        mock = []
        self.returns = [mock]
        d = self.group.get_policy('3444')
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"tenantId": "11111", "groupId": "12345678", "policyId": "3444"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.flushLoggedErrors(NoSuchPolicyError)

    def test_view_policy_no_version(self):
        """
        When viewing the policy, any version information is removed from the
        final output
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{"_ver": 5}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.get_policy("3444")
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {})

    def test_list_policy(self):
        """
        Test that you can list a bunch of scaling policies.
        """
        mock = [
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group1', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{}', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group3', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{}', 'ttl': None}], 'key': ''}]
        self.returns = [mock]
        expectedData = {"groupId": '12345678',
                        "tenantId": '11111'}
        expectedCql = ('SELECT "policyId", data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND deleted = False;')
        d = self.group.list_policies()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 2)
        self.assertEqual(r, {'group1': {}, 'group3': {}})

        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_list_policy_empty_list(self):
        """
        If the group exists but there are no policies, `list_policies` returns
        an empty list
        """
        def execute_respond(cql, cqlargs, *other_args, **kwargs):
            if 'scaling_config' in cql:  # view config - seeing if it's there
                return defer.succeed([
                    {'cols': [{'timestamp': None,
                               'name': 'data',
                               'value': '{"_ver": 5}',
                               'ttl': None}],
                     'key': ''}])
            else:
                return defer.succeed([])
        self.connection.execute.side_effect = execute_respond

        result = self.assert_deferred_succeeded(self.group.list_policies())
        self.assertEqual(result, {})

    def test_list_policy_invalid_group(self):
        """
        If the group does not exist, `list_policies` raises a
        :class:`NoSuchScalingGroupError`
        """
        def execute_respond(cql, cqlargs, *other_args, **kwargs):
            if 'scaling_config' in cql:  # view config - seeing if it's there
                return defer.succeed([])  # no config - no such group
            else:
                return defer.succeed([])
        self.connection.execute.side_effect = execute_respond

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
        mock = [
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group1', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{"_ver": 5}', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'policyId',
                       'value': 'group3', 'ttl': None},
                      {'timestamp': None, 'name': 'data',
                       'value': '{"_ver": 2}', 'ttl': None}], 'key': ''}]
        self.returns = [mock]
        d = self.group.list_policies()
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(r, {'group1': {}, 'group3': {}})

    def test_add_scaling_policy(self):
        """
        Test that you can add a scaling policy, and what is returned is a
        dictionary of the ids to the scaling policies
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.create_policies([{"b": "lah"}])
        result = self.assert_deferred_succeeded(d)
        expectedCql = ('BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", '
                       'data, deleted) VALUES (:tenantId, :groupId, :policy0Id, :policy0, False) '
                       'APPLY BATCH;')
        expectedData = {"policy0": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "policy0Id": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

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
        expectedData = {"tenantId": "11111", "groupId": "12345678", "policyId": "3222"}

        self.assertEqual(len(self.connection.execute.mock_calls), 2)  # view, delete
        self.connection.execute.assert_called_with(expectedCql,
                                                   expectedData, ConsistencyLevel.ONE)

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
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.assertIsNone(self.assert_deferred_succeeded(d))  # update returns None
        expectedCql = (
            'BEGIN BATCH INSERT INTO scaling_policies("tenantId", "groupId", "policyId", data) '
            'VALUES (:tenantId, :groupId, :policyId, :policy) APPLY BATCH;')
        expectedData = {"policy": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

    def test_update_scaling_policy_bad(self):
        """
        Tests that if you try to update a scaling policy that doesn't exist, the right thing happens
        """
        self.returns = [[], None]
        d = self.group.update_policy('12345678', {"b": "lah"})
        self.assert_deferred_failed(d, NoSuchPolicyError)
        expectedCql = ('SELECT data FROM scaling_policies WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
        expectedData = {"groupId": '12345678',
                        "policyId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
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
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

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


class CassScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`CassScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock()

        self.connection.execute.return_value = defer.succeed(None)
        self.collection = CassScalingGroupCollection(self.connection)
        self.tenant_id = 'goo1234'
        self.config = {
            'name': 'blah',
            'cooldown': 600,
            'minEntities': 0,
            'maxEntities': 10,
            'metadata': {}
        }
        self.hashkey_patch = mock.patch(
            'otter.models.cass.generate_key_str')
        self.mock_key = self.hashkey_patch.start()
        self.addCleanup(self.hashkey_patch.stop)

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
        d = self.collection.create_scaling_group('123', {}, {})
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.ONE)

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
        d = self.collection.create_scaling_group('123', {}, {}, [{}])
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.ONE)

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
        d = self.collection.create_scaling_group('123', {}, {}, [{}, {}])
        self.assertEqual(self.assert_deferred_succeeded(d),
                         self.mock_key.return_value)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.ONE)

    def test_list(self):
        """
        Test that you can list a bunch of configs.
        """
        mockdata = [
            {'cols': [{'timestamp': None, 'name': 'groupId',
                       'value': 'group1', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'groupId',
                       'value': 'group3', 'ttl': None}], 'key': ''}]

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "groupId" FROM scaling_config WHERE "tenantId" = :tenantId '
                       'AND deleted = False;')
        self.connection.execute.return_value = defer.succeed(mockdata)
        d = self.collection.list_scaling_groups('123')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 2)
        for row in r:
            self.assertEqual(row.tenant_id, '123')
        self.assertEqual(r[0].uuid, 'group1')
        self.assertEqual(r[1].uuid, 'group3')
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_list_empty(self):
        """
        Test that you can list a bunch of configs.
        """
        mockdata = []

        expectedData = {'tenantId': '123'}
        expectedCql = ('SELECT "groupId" FROM scaling_config WHERE "tenantId" = :tenantId '
                       'AND deleted = False;')
        self.connection.execute.return_value = defer.succeed(mockdata)
        d = self.collection.list_scaling_groups('123')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 0)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

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
            self.connection.execute.return_value = defer.succeed(bad)
            self.assert_deferred_failed(self.collection.list_scaling_groups('123'),
                                        CassBadDataError)
            self.flushLoggedErrors(CassBadDataError)

    def test_get_scaling_group(self):
        """
        Tests that you can get a scaling group
        (note that it doesn't request the database)
        """
        g = self.collection.get_scaling_group('123', '12345678')
        self.assertTrue(isinstance(g, CassScalingGroup))
        self.assertEqual(g.uuid, '12345678')
        self.assertEqual(g.tenant_id, '123')

    def test_delete_non_existant_scaling_group_fails(self):
        """
        If the scaling group doesn't exist, :class:`NoSuchScalingGroup` is
        raised
        """
        execute_results = [[], None]  # view returns an empty list

        def execute_respond(*args, **kwargs):
            return defer.succeed(execute_results.pop(0))

        self.connection.execute.side_effect = execute_respond

        self.assert_deferred_failed(
            self.collection.delete_scaling_group('123', 'group1'),
            NoSuchScalingGroupError)
        self.flushLoggedErrors(NoSuchScalingGroupError)
        # only called once to view
        self.assertEqual(len(self.connection.execute.mock_calls), 1)

    def test_delete_existing_scaling_group(self):
        """
        If the scaling group exists, deletes scaling group
        """
        view_config = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        execute_results = [view_config, None]  # executing update returns None

        def execute_respond(*args, **kwargs):
            return defer.succeed(execute_results.pop(0))

        self.connection.execute.side_effect = execute_respond

        result = self.assert_deferred_succeeded(
            self.collection.delete_scaling_group('123', 'group1'))
        self.assertIsNone(result)  # delete returns None
        # called twice - once to view and once to delete
        self.assertEqual(len(self.connection.execute.mock_calls), 2)

        expected_data = {'tenantId': '123', 'groupId': 'group1'}
        expected_cql = (
            'BEGIN BATCH '
            'UPDATE scaling_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'UPDATE launch_config SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'UPDATE scaling_policies SET deleted=True '
            'WHERE "tenantId" = :tenantId AND "groupId" = :groupId '
            'APPLY BATCH;')

        self.connection.execute.assert_called_with(expected_cql, expected_data,
                                                   ConsistencyLevel.ONE)
