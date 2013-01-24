"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.models.cass import (
    CassScalingGroup,
    CassScalingGroupCollection,
    CassBadDataError)

from otter.models.interface import NoSuchScalingGroupError

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
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.assertEqual(r, {})

    def test_view_config_corrupt(self):
        """
        Test what happens if you retrieve a corrupt JSON record (e.g. database corruption)
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{ff}',
                       'ttl': None}],
             'key': ''}]
        self.returns = [mock]
        d = self.group.view_config()
        self.assert_deferred_failed(d, CassBadDataError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_view_config_empty(self):
        """
        Tests what happens if you try to view a group that doesn't exist.
        """
        mock = []
        self.returns = [mock]
        d = self.group.view_config()
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_view_config_bad(self):
        """
        This should probably never happen, but just in case, make sure
        that it does the right thing
        """
        mock = [{}]
        self.returns = [mock]
        d = self.group.view_config()
        self.assert_deferred_failed(d, CassBadDataError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_view_config_none(self):
        """
        This should probably never happen, but just in case, make sure
        that it does the right thing
        """
        mock = None
        self.returns = [mock]
        d = self.group.view_config()
        self.assert_deferred_failed(d, CassBadDataError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

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
        expectedCql = "SELECT data FROM launch_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)
        self.assertEqual(r, {})

    def test_update_config(self):
        """
        Test that you can update a config
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.update_config({"b": "lah"})
        self.assert_deferred_succeeded(d)
        expectedCql = "BEGIN BATCH INSERT INTO scaling_config(tenantId, groupId, data) VALUES "
        expectedCql += "(:tenantId, :groupId, :scaling) APPLY BATCH;"
        expectedData = {"scaling": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)

    def test_update_bad(self):
        """
        Tests that you can't just create a scaling group by sending
        an update to a nonexistant group
        """
        self.returns = [[], None]
        d = self.group.update_config({"b": "lah"})
        self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql += "tenantId = :tenantId AND groupId = :groupId AND deleted = False;"
        expectedData = {"tenantId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_update_launch(self):
        """
        Test that you can update a launch config
        """
        mock = [
            {'cols': [{'timestamp': None,
                       'name': 'data',
                       'value': '{}',
                       'ttl': None}],
             'key': ''}]

        self.returns = [mock, None]
        d = self.group.update_launch_config({"b": "lah"})
        self.assert_deferred_succeeded(d)
        expectedCql = "BEGIN BATCH INSERT INTO launch_config(tenantId, groupId, data) VALUES "
        expectedCql += "(:tenantId, :groupId, :launch) APPLY BATCH;"
        expectedData = {"launch": '{"_ver": 1, "b": "lah"}',
                        "groupId": '12345678',
                        "tenantId": '11111'}
        self.connection.execute.assert_called_with(
            expectedCql, expectedData, ConsistencyLevel.ONE)


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

    def tearDown(self):
        """ Stop patching the generate_random_str """
        self.hashkey_patch.stop()

    def test_create(self):
        """
        Test that you can create a group
        """
        expectedData = {
            'scaling': '{"_ver": 1}',
            'launch': '{"_ver": 1}',
            'groupId': '12345678',
            'tenantId': '123'}
        expectedCql = "BEGIN BATCH INSERT INTO scaling_config(tenantId, "
        expectedCql += "groupId, data, deleted) VALUES (:tenantId, :groupId, "
        expectedCql += ":scaling, False) INSERT INTO launch_config(tenantId, "
        expectedCql += "groupId, data, deleted) VALUES (:tenantId, :groupId, :launch, False) "
        expectedCql += "APPLY BATCH;"
        self.mock_key.return_value = '12345678'
        d = self.collection.create_scaling_group('123', {}, {})
        self.assert_deferred_succeeded(d)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData,
                                                        ConsistencyLevel.ONE)

    def test_list(self):
        """
        Test that you can list a bunch of configs.
        """
        mockdata = [
            {'cols': [{'timestamp': None, 'name': 'groupid',
                       'value': 'group1', 'ttl': None}], 'key': ''},
            {'cols': [{'timestamp': None, 'name': 'groupid',
                       'value': 'group3', 'ttl': None}], 'key': ''}]

        expectedData = {'tenantId': '123'}
        expectedCql = "SELECT groupid FROM scaling_config WHERE tenantId = :tenantId "
        expectedCql += "AND deleted = False;"
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
        expectedCql = "SELECT groupid FROM scaling_config WHERE tenantId = :tenantId "
        expectedCql += "AND deleted = False;"
        self.connection.execute.return_value = defer.succeed(mockdata)
        d = self.collection.list_scaling_groups('123')
        r = self.assert_deferred_succeeded(d)
        self.assertEqual(len(r), 0)
        self.connection.execute.assert_called_once_with(expectedCql,
                                                        expectedData)

    def test_get(self):
        """
        Tests that you can get a config
        (note that it doesn't request the database)
        """
        g = self.collection.get_scaling_group('123', '12345678')
        self.assertEqual(g.uuid, '12345678')
        self.assertEqual(g.tenant_id, '123')
