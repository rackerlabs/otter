"""
Tests for the otter-api tap plugin.
"""

import json
import mock

from twisted.internet import reactor

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.tap.api import Options, makeService
from otter.test.utils import patch


test_config = {
    'port': 'tcp:9999',
    'cassandra': {
        'seed_hosts': ['tcp:127.0.0.1:9160'],
        'keyspace': 'otter_test'
    },
    'environment': 'prod'
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
        self.service = patch(self, 'otter.tap.api.service')
        self.Site = patch(self, 'otter.tap.api.Site')
        self.clientFromString = patch(self, 'otter.tap.api.clientFromString')

        self.RoundRobinCassandraCluster = patch(self, 'otter.tap.api.RoundRobinCassandraCluster')
        self.LoggingCQLClient = patch(self, 'otter.tap.api.LoggingCQLClient')
        self.log = patch(self, 'otter.tap.api.log')

        Otter_patcher = mock.patch('otter.tap.api.Otter')
        self.Otter = Otter_patcher.start()
        self.addCleanup(Otter_patcher.stop)

        self.CassScalingGroupCollection = patch(self, 'otter.tap.api.CassScalingGroupCollection')

        SchedulerService_patcher = mock.patch('otter.tap.api.SchedulerService')
        self.SchedulerService = SchedulerService_patcher.start()
        self.addCleanup(SchedulerService_patcher.stop)

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
        self.log.bind.assert_called_once_with(system='otter.silverberg')
        self.LoggingCQLClient.assert_called_once_with(self.RoundRobinCassandraCluster.return_value,
                                                      self.log.bind.return_value)
        self.CassScalingGroupCollection.assert_called_once_with(self.LoggingCQLClient.return_value)

    def test_cassandra_store(self):
        """
        makeService configures the CassScalingGroupCollection as the
        api store.
        """
        makeService(test_config)
        self.Otter.assert_called_once_with(self.CassScalingGroupCollection.return_value)

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
                       self.clientFromString):
            mock_calls = getattr(mocked, 'mock_calls')
            self.assertEqual(len(mock_calls), 0,
                             "{0} called with {1}".format(mocked, mock_calls))

    def test_mock_store_with_scheduler(self):
        """
        makeService does not setup a SchedulerService when Cassandra is
        mocked, and a scheduler config exists.
        """
        mock_config = test_config.copy()
        mock_config['mock'] = True
        mock_config['scheduler'] = {'interval': 1, 'batchsize': 5}

        makeService(mock_config)

        for mocked in (self.RoundRobinCassandraCluster,
                       self.LoggingCQLClient,
                       self.CassScalingGroupCollection,
                       self.SchedulerService,
                       self.clientFromString):
            mock_calls = getattr(mocked, 'mock_calls')
            self.assertEqual(len(mock_calls), 0,
                             "{0} called with {1}".format(mocked, mock_calls))

    @mock.patch('otter.tap.api.SchedulerService')
    def test_scheduler_service(self, scheduler_service):
        """
        SchedulerService is added to MultiService when 'scheduler' settings are there in config file
        """
        mock_config = test_config.copy()
        mock_config['scheduler'] = {'interval': 10, 'batchsize': 100}

        expected_parent = makeService(mock_config)
        scheduler_service.assert_called_once_with(100, 10,
                                                  self.LoggingCQLClient.return_value,
                                                  self.CassScalingGroupCollection.return_value)
        scheduler_service.return_value.setServiceParent.assert_called_with(expected_parent)
