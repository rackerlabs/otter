"""
Tests for the otter-api tap plugin.
"""

import json
import mock

from twisted.internet import reactor

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.tap.api import Options, makeService

test_config = {
    'port': 'tcp:9999',
    'cassandra': {
        'seed_hosts': ['tcp:127.0.0.1:9160'],
        'keyspace': 'otter_test'
    }
}


class APIOptionsTests(TestCase):
    """
    Test the various command line options.
    """
    def setUp(self):
        """
        Configure mocks for the jsonfig config library.
        """
        jsonfig_patcher = mock.patch('otter.tap.api.jsonfig')
        self.jsonfig = jsonfig_patcher.start()
        self.addCleanup(jsonfig_patcher.stop)

        self.jsonfig.from_path.return_value = test_config

    def test_port_options(self):
        """
        The port long option should end up in the 'port' key.
        """
        config = Options()
        config.parseOptions(['--port=tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')

    def test_short_port_options(self):
        """
        The p short option should end up in the 'port' key.
        """
        config = Options()
        config.parseOptions(['-p', 'tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')

    def test_store_options(self):
        """
        The mock long flag option should end up in the 'mock' key
        """
        config = Options()
        self.assertFalse(config['mock'])
        config.parseOptions(['--mock'])
        self.assertTrue(config['mock'])

    def test_short_store_options(self):
        """
        The m shor toption should end up in the 'mock' key
        """
        config = Options()
        self.assertFalse(config['mock'])
        config.parseOptions(['-m'])
        self.assertTrue(config['mock'])


class APIMakeServiceTests(TestCase):
    """
    Test creation of the API service heirarchy.
    """
    def setUp(self):
        """
        Configure mocks for Site and the strports service constructor.
        """
        service_patcher = mock.patch('otter.tap.api.service')
        self.service = service_patcher.start()
        self.addCleanup(service_patcher.stop)

        site_patcher = mock.patch('otter.tap.api.Site')
        self.Site = site_patcher.start()
        self.addCleanup(site_patcher.stop)

        clientFromString_patcher = mock.patch('otter.tap.api.clientFromString')
        self.clientFromString = clientFromString_patcher.start()
        self.addCleanup(clientFromString_patcher.stop)

        RoundRobinCassandraCluster_patcher = mock.patch('otter.tap.api.RoundRobinCassandraCluster')
        self.RoundRobinCassandraCluster = RoundRobinCassandraCluster_patcher.start()
        self.addCleanup(RoundRobinCassandraCluster_patcher.stop)

        set_store_patcher = mock.patch('otter.tap.api.set_store')
        self.set_store = set_store_patcher.start()
        self.addCleanup(set_store_patcher.stop)

        CassScalingGroupCollection_patcher = mock.patch('otter.tap.api.CassScalingGroupCollection')
        self.CassScalingGroupCollection = CassScalingGroupCollection_patcher.start()
        self.addCleanup(CassScalingGroupCollection_patcher.stop)

    def test_service_site_on_port(self):
        """
        makeService will create a strports service on tcp:9999 with a
        Site instance.
        """
        makeService(test_config)
        self.service.assert_called_with('tcp:9999', self.Site.return_value)

    def test_unicode_service_site_on_port(self):
        """
        makeService will create strports service with a byte endpoint string
        even if config was given in unicode
        """
        unicode_config = json.loads(json.dumps(test_config, encoding="utf-8"))
        makeService(unicode_config)
        self.service.assert_called_with('tcp:9999', self.Site.return_value)
        self.assertTrue(isinstance(self.service.call_args[0][0], str))

    def test_is_MultiService(self):
        """
        makeService will return a MultiService.
        """
        self.assertIsInstance(makeService(test_config), MultiService)

    def test_service_is_added_to_MultiService(self):
        """
        makeService will set the parent of the strports service as the
        returned MultiService.
        """
        expected_parent = makeService(test_config)
        self.service.return_value.setServiceParent.assert_called_with(expected_parent)

    def test_cassandra_seed_hosts_endpoints(self):
        """
        makeService will create a client endpoint for each address in the
        cassandra seed_hosts.
        """
        makeService(test_config)
        self.clientFromString.assert_called_once_with(reactor, 'tcp:127.0.0.1:9160')

    def test_unicode_cassandra_seed_hosts_endpoints(self):
        """
        makeService will create a client endpoint for each address in the
        cassandra seed_hosts with a byte endpoint string even if config was
        given in unicode
        """
        unicode_config = json.loads(json.dumps(test_config, encoding="utf-8"))
        makeService(unicode_config)
        self.clientFromString.assert_called_once_with(reactor, 'tcp:127.0.0.1:9160')
        self.assertTrue(isinstance(self.clientFromString.call_args[0][1], str))

    def test_cassandra_cluster_with_endpoints_and_keyspace(self):
        """
        makeService configures a RoundRobinCassandraCluster with the
        seed_endpoints and the keyspace from the config.
        """
        makeService(test_config)
        self.RoundRobinCassandraCluster.assert_called_once_with(
            [self.clientFromString.return_value],
            'otter_test')

    def test_cassandra_scaling_group_collection_with_cluster(self):
        """
        makeService configures a CassScalingGroupCollection with the
        cassandra cluster connection.
        """
        makeService(test_config)
        self.CassScalingGroupCollection.assert_called_once_with(
            self.RoundRobinCassandraCluster.return_value)

    def test_cassandra_store(self):
        """
        makeService configures the CassScalingGroupCollection as the
        api store.
        """
        makeService(test_config)
        self.set_store.assert_called_once_with(
            self.CassScalingGroupCollection.return_value)

    def test_mock_store(self):
        """
        makeService does not configure the CassScalingGroupCollection as an
        api store
        """
        mock_config = test_config.copy()
        mock_config['mock'] = True
        makeService(mock_config)

        for mocked in (self.RoundRobinCassandraCluster,
                       self.CassScalingGroupCollection,
                       self.set_store, self.clientFromString):
            mock_calls = getattr(mocked, 'mock_calls')
            self.assertEqual(len(mock_calls), 0,
                             "{0} called with {1}".format(mocked, mock_calls))

    @mock.patch('otter.tap.api.GraylogUDPPublisher')
    @mock.patch('otter.tap.api.log.addObserver')
    def test_graylog(self, addObserver, GraylogUDPPublisher):
        """
        makeService configures adds log observer when graylog is in the config.
        """
        mock_config = test_config.copy()
        mock_config['graylog'] = {'host': '127.0.0.1', 'port': 12211}

        makeService(mock_config)

        # It's pretty hard to actually tell what the observer is, so we assume
        # if addObserver was called once, and GraylogUDPPublisher was called,
        # we set things up correctly.
        addObserver.assert_called_once_with(mock.ANY)

        GraylogUDPPublisher.assert_called_once_with(**mock_config['graylog'])
