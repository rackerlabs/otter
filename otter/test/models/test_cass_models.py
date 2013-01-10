"""
Tests for :mod:`otter.models.mock`
"""
import mock

from twisted.trial.unittest import TestCase

from otter.models.cass import (
    CassScalingGroup, 
    CassScalingGroupCollection,
    CassBadDataError)
    
from otter.models.interface import NoSuchScalingGroupError, NoSuchEntityError

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
        cflist = {"config": "scaling_config",
                  "launch": "launch_config",
                  "policies": "policies"}
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
        self.group = CassScalingGroup(self.tenant_id,'12345678',
                                      self.connection, cflist)
#        self.group = MockScalingGroup(
#            self.tenant_id, 1,
#            {'config': self.config, 'launch': self.launch_config,
#             'policies': self.policies})

    def test_view_config(self):
        mock = [
                {'cols': [{'timestamp': None, 
                           'name': 'data', 
                           'value': '{}', 
                           'ttl': None}], 
                 'key': ''}]
        self.connection.execute.return_value = defer.succeed(mock)
        d = self.group.view_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql +=  "accountId = :accountId AND groupId = :groupId;"
        expectedData = {"accountId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData)

    def test_view_config_corrupt(self):
        mock = [
                {'cols': [{'timestamp': None, 
                           'name': 'data', 
                           'value': '{ff}', 
                           'ttl': None}], 
                 'key': ''}]
        self.connection.execute.return_value = defer.succeed(mock)
        d = self.group.view_config()
        r = self.assert_deferred_failed(d, CassBadDataError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql +=  "accountId = :accountId AND groupId = :groupId;"
        expectedData = {"accountId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData)

    def test_view_config_empty(self):
        mock = []
        self.connection.execute.return_value = defer.succeed(mock)
        d = self.group.view_config()
        r = self.assert_deferred_failed(d, NoSuchScalingGroupError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql +=  "accountId = :accountId AND groupId = :groupId;"
        expectedData = {"accountId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData)

    def test_view_config_bad(self):
        mock = [{}]
        self.connection.execute.return_value = defer.succeed(mock)
        d = self.group.view_config()
        r = self.assert_deferred_failed(d, CassBadDataError)
        expectedCql = "SELECT data FROM scaling_config WHERE "
        expectedCql +=  "accountId = :accountId AND groupId = :groupId;"
        expectedData = {"accountId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData)

    def test_view_launch(self):
        mock = [
                {'cols': [{'timestamp': None, 
                           'name': 'data', 
                           'value': '{}', 
                           'ttl': None}], 
                 'key': ''}]
        self.connection.execute.return_value = defer.succeed(mock)
        d = self.group.view_launch_config()
        r = self.assert_deferred_succeeded(d)
        expectedCql = "SELECT data FROM launch_config WHERE "
        expectedCql +=  "accountId = :accountId AND groupId = :groupId;"
        expectedData = {"accountId": "11111", "groupId": "12345678"}
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData)


class MockScalingGroupsCollectionTestCase(IScalingGroupCollectionProviderMixin,
                                          TestCase):
    """
    Tests for :class:`MockScalingGroupCollection`
    """

    def setUp(self):
        """ Setup the mocks """
        self.connection = mock.MagicMock()
        self.connection.execute.return_value = defer.succeed(None)
        cflist = {"config": "scaling_config",
                  "launch": "launch_config",
                  "policies": "policies"}
        self.collection = CassScalingGroupCollection(self.connection, cflist)
        self.tenant_id = 'goo1234'
        self.config = {
            'name': 'blah',
            'cooldown': 600,
            'minEntities': 0,
            'maxEntities': 10,
            'metadata': {}
        }
        self.hashkey_patch = mock.patch(
            'otter.models.cass.generate_random_str')
        self.mock_key = self.hashkey_patch.start()
        
    def tearDown(self):
        self.hashkey_patch.stop()
        
    def test_create(self):
        expectedData = {
            'scaling': {},
            'launch': {},
            'groupId': '12345678',
            'accountId': '123'}
        expectedCql = "BEGIN BATCH INSERT INTO scaling_config(accountId, "
        expectedCql += "groupId, data) VALUES (:accountId, :groupId, "
        expectedCql += ":scaling) INSERT INTO launch_config(accountId, "
        expectedCql += "groupId, data) VALUES (:accountId, :groupId, :launch) "
        expectedCql += "APPLY BATCH;"
        self.mock_key.return_value = '12345678'
        d = self.collection.create_scaling_group('123', {}, {})
        r = self.assert_deferred_succeeded(d)
        self.connection.execute.assert_called_once_with(expectedCql, 
                                                        expectedData, 
                                                        ConsistencyLevel.ONE)
    def test_get(self):
        g = self.collection.get_scaling_group('123', '12345678')
        self.assertEqual(g.uuid,'12345678')
        self.assertEqual(g.tenant_id,'123')
