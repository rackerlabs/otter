"""
Tests for the otter-api tap plugin.
"""

import json
import mock

from twisted.internet import reactor, defer

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.supervisor import get_supervisor, set_supervisor, SupervisorService
from otter.tap.api import Options, makeService, setup_scheduler
from otter.test.utils import patch, CheckFailure
from otter.util.config import set_config_data


test_config = {
    'port': 'tcp:9999',
    'admin': 'tcp:9789',
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
        The m short option should end up in the 'mock' key
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
        self.store = self.CassScalingGroupCollection.return_value

    def test_service_site_on_port(self):
        """
        makeService will create a strports service on tcp:9999 with a
        Site instance.
        """
        makeService(test_config)
        self.service.assert_any_call('tcp:9999', self.Site.return_value)

    def test_admin_site_on_port(self):
        """
        makeService will create a strports admin service on tcp:9789 with a
        Site instance.
        """
        makeService(test_config)
        self.service.assert_any_call('tcp:9789', self.Site.return_value)

    def test_no_admin(self):
        """
        makeService does not create admin service if admin config value is
        not there
        """
        config = test_config.copy()
        del config['admin']
        makeService(config)
        self.assertTrue('tcp:9789' not in [args[0] for args, _ in self.service.call_args_list])

    def test_unicode_service_site_on_port(self):
        """
        makeService will create strports service with a byte endpoint string
        even if config was given in unicode
        """
        unicode_config = json.loads(json.dumps(test_config, encoding="utf-8"))
        makeService(unicode_config)
        self.service.assert_any_call('tcp:9999', self.Site.return_value)
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
        self.Otter.assert_called_once_with(self.store, None)

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

    def test_api_config_options(self):
        """
        makeService passes api config options to Otter if specified
        """
        api_config = {
            'launch_config_validation': True
        }

        makeService(dict(api=api_config, **test_config))
        self.Otter.assert_called_once_with(self.store, api_config)

    @mock.patch('otter.tap.api.SupervisorService', wraps=SupervisorService)
    def test_supervisor_service_set_by_default(self, supervisor):
        """
        A SupervisorService service is added to the Multiservice, and set as
        default supervisor
        """
        self.addCleanup(lambda: set_supervisor(None))
        parent = makeService(test_config)
        supervisor_service = parent.getServiceNamed('supervisor')

        self.assertEqual(get_supervisor(), supervisor_service)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    def test_kazoo_client_success(self, mock_txkz, mock_setup_scheduler):
        """
        TxKazooClient is started and calls `setup_scheduler`. Its instance
        is also set in store.kz_client after start has finished
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}

        kz_client = mock.Mock(spec=['start'])
        start_d = defer.Deferred()
        kz_client.start.return_value = start_d
        mock_txkz.return_value = kz_client
        self.store.kz_client = None

        parent = makeService(config)

        mock_txkz.assert_called_once_with(hosts='zk_hosts', threads=20)
        kz_client.start.assert_called_once_with()

        # setup_scheduler and store.kz_client is not called yet
        self.assertFalse(mock_setup_scheduler.called)
        self.assertIsNone(self.store.kz_client)

        # they are called after start completes
        start_d.callback(None)
        mock_setup_scheduler.assert_called_once_with(parent, self.store, kz_client)
        self.assertEqual(self.store.kz_client, kz_client)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    def test_kazoo_client_failed(self, mock_txkz, mock_setup_scheduler):
        """
        `setup_scheduler` is not called if TxKazooClient is not able to start
        Error is logged
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start'])
        kz_client.start.return_value = defer.fail(ValueError('e'))
        mock_txkz.return_value = kz_client

        makeService(config)

        mock_txkz.assert_called_once_with(hosts='zk_hosts', threads=20)
        kz_client.start.assert_called_once_with()
        self.assertFalse(mock_setup_scheduler.called)
        self.log.err.assert_called_once_with(CheckFailure(ValueError),
                                             'Could not start TxKazooClient')


class SchedulerSetupTests(TestCase):
    """
    Tests for `setup_scheduler`
    """

    def setUp(self):
        """
        Mock args
        """
        self.scheduler_service = patch(self, 'otter.tap.api.SchedulerService')
        self.config = {
            'scheduler': {
                'buckets': 10,
                'partition': {'path': '/part_path', 'time_boundary': 15},
                'batchsize': 100,
                'interval': 10
            }
        }
        set_config_data(self.config)
        self.parent = mock.Mock()
        self.store = mock.Mock()
        self.kz_client = mock.Mock()

    def tearDown(self):
        """
        Rest config data
        """
        set_config_data({})

    def test_success(self):
        """
        `SchedulerService` is configured with config values and set as parent
        to passed `MultiService`
        """
        setup_scheduler(self.parent, self.store, self.kz_client)
        buckets = range(1, 11)
        self.store.set_scheduler_buckets.assert_called_once_with(buckets)
        self.scheduler_service.assert_called_once_with(
            100, 10, self.store, self.kz_client, '/part_path', 15, buckets)
        self.scheduler_service.return_value.setServiceParent.assert_called_once_with(self.parent)

    def test_mock_store_with_scheduler(self):
        """
        SchedulerService is not created with mock store
        """
        self.config['mock'] = True
        set_config_data(self.config)

        setup_scheduler(self.parent, self.store, self.kz_client)

        self.assertFalse(self.store.set_scheduler_buckets.called)
        self.assertFalse(self.scheduler_service.called)
