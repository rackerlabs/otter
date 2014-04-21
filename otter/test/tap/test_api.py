"""
Tests for the otter-api tap plugin.
"""

import json
import mock

from testtools.matchers import Contains

from twisted.internet import reactor, defer

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.supervisor import get_supervisor, set_supervisor, SupervisorService
from otter.tap.api import (
    Options, HealthChecker, makeService, setup_scheduler, call_after_supervisor)
from otter.test.utils import matches, patch, CheckFailure
from otter.util.config import set_config_data
from otter.util.deferredutils import DeferredPool


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


class HealthCheckerTests(TestCase):
    """
    Tests for the HealthChecker object
    """
    def test_no_checks(self):
        """
        If there are no checks, HealthChecker returns healthy
        """
        checker = HealthChecker()
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {'healthy': True})

    def test_invalid_check(self):
        """
        If an invalid check is added, its health is unhealthy
        """
        checker = HealthChecker({'invalid': None})
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': False,
            'invalid': {
                'healthy': False,
                'details': {'reason': mock.ANY}
            }
        })

    def test_check_failure(self):
        """
        If a check raises an exception, its health is unhealthy
        """
        checker = HealthChecker({'fail': mock.Mock(side_effect=Exception)})
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': False,
            'fail': {
                'healthy': False,
                'details': {'reason': matches(Contains('Exception'))}
            }
        })

    def test_synchronous_health_check(self):
        """
        Synchronous health checks are supported
        """
        checker = HealthChecker({'sync': mock.Mock(return_value=(True, {}))})
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': True,
            'sync': {
                'healthy': True,
                'details': {}
            }
        })

    def test_asynchronous_health_check(self):
        """
        Asynchronous health checks are supported
        """
        checker = HealthChecker(
            {'sync': mock.Mock(return_value=defer.succeed((True, {})))})
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': True,
            'sync': {
                'healthy': True,
                'details': {}
            }
        })

    def test_one_failed_health_fails_overall_health(self):
        """
        All health checks must pass in order for the main check to be healthy
        """
        checker = HealthChecker({
            'healthy_thing': mock.Mock(return_value=(True, {})),
            'unhealthy_thing': mock.Mock(return_value=(False, {}))
        })
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': False,
            'healthy_thing': {
                'healthy': True,
                'details': {}
            },
            'unhealthy_thing': {
                'healthy': False,
                'details': {}
            }
        })

    def test_all_health_passes_means_overall_health_passes(self):
        """
        When all health checks pass the overall check is healthy
        """
        checker = HealthChecker(dict([
            ("check{0}".format(i), mock.Mock(return_value=(True, {})))
            for i in range(3)
        ]))
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {
            'healthy': True,
            'check0': {
                'healthy': True,
                'details': {}
            },
            'check1': {
                'healthy': True,
                'details': {}
            },
            'check2': {
                'healthy': True,
                'details': {}
            }
        })


class CallAfterSupervisorTests(TestCase):
    """
    Tests for `call_after_supervisor`
    """

    def test_calls_after_supervisor_finishes(self):
        """
        Func is called after supervisor is completed stopped
        """
        supervisor = mock.Mock(spec=['deferred_pool'])
        supervisor.deferred_pool = mock.Mock(spec=DeferredPool)
        supervisor.deferred_pool.notify_when_empty.return_value = defer.Deferred()
        func = mock.Mock(return_value=defer.succeed(2))

        d = call_after_supervisor(func, supervisor)

        # No result
        self.assertNoResult(d)
        supervisor.deferred_pool.notify_when_empty.assert_called_once_with()
        self.assertFalse(func.called)

        # Supervisor jobs are completed and func is called
        supervisor.deferred_pool.notify_when_empty.return_value.callback(None)
        func.assert_called_once_with()
        self.assertEqual(self.successResultOf(d), 2)


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

        self.health_checker = None

        def make_health_checker(*args, **kwargs):
            self.health_checker = HealthChecker(*args, **kwargs)
            return self.health_checker

        patch(self, 'otter.tap.api.HealthChecker', side_effect=make_health_checker)

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

    def test_cassandra_cluster_disconnects_on_stop(self):
        """
        Cassandra cluster connection is disconnected when main service is stopped
        """
        service = makeService(test_config)
        service.stopService()

        self.LoggingCQLClient.return_value.disconnect.assert_called_once_with()

    def test_cassandra_store(self):
        """
        makeService configures the CassScalingGroupCollection as the
        api store
        """
        makeService(test_config)
        self.Otter.assert_called_once_with(self.store,
                                           self.health_checker.health_check)

    def test_health_checker_no_zookeeper(self):
        """
        A health checker is constructed by default with the store
        """
        self.assertIsNone(self.health_checker)
        makeService(test_config)
        self.assertIsNotNone(self.health_checker)
        self.assertEqual(self.health_checker.checks['store'],
                         self.store.health_check)

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
        is also set in store.kz_client after start has finished, and the
        scheduler added to the health checker
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}

        kz_client = mock.Mock(spec=['start', 'stop'])
        start_d = defer.Deferred()
        kz_client.start.return_value = start_d
        mock_txkz.return_value = kz_client
        self.store.kz_client = None

        parent = makeService(config)

        self.log.bind.assert_called_with(system='kazoo')
        mock_txkz.assert_called_once_with(
            hosts='zk_hosts', threads=20, txlog=self.log.bind.return_value)
        kz_client.start.assert_called_once_with()

        # setup_scheduler and store.kz_client is not called yet, and nothing
        # added to the health checker
        self.assertFalse(mock_setup_scheduler.called)
        self.assertIsNone(self.store.kz_client)

        # they are called after start completes
        start_d.callback(None)
        mock_setup_scheduler.assert_called_once_with(parent, self.store, kz_client)
        self.assertEqual(self.store.kz_client, kz_client)
        sch = mock_setup_scheduler.return_value
        self.assertEqual(self.health_checker.checks['scheduler'], sch.health_check)
        self.assertEqual(self.Otter.return_value.scheduler_reset, sch.reset)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    def test_kazoo_client_failed(self, mock_txkz, mock_setup_scheduler):
        """
        `setup_scheduler` is not called if TxKazooClient is not able to start
        Error is logged
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.fail(ValueError('e'))
        mock_txkz.return_value = kz_client

        makeService(config)

        mock_txkz.assert_called_once_with(
            hosts='zk_hosts', threads=20, txlog=mock.ANY)
        kz_client.start.assert_called_once_with()
        self.assertFalse(mock_setup_scheduler.called)
        self.log.err.assert_called_once_with(CheckFailure(ValueError),
                                             'Could not start TxKazooClient')

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    def test_kazoo_client_stops(self, mock_txkz, mock_setup_scheduler):
        """
        TxKazooClient is stopped when parent service stops
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.succeed(None)
        mock_txkz.return_value = kz_client
        self.store.kz_client = None

        parent = makeService(config)

        kz_client.stop.return_value = defer.Deferred()
        d = parent.stopService()

        self.assertTrue(kz_client.stop.called)
        self.assertNoResult(d)
        kz_client.stop.return_value.callback(None)
        self.successResultOf(d)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    def test_kazoo_client_stops_after_supervisor(self, mock_txkz, mock_setup_scheduler):
        """
        Kazoo is stopped after supervisor stops
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.succeed(None)
        kz_client.stop.return_value = defer.succeed(None)
        mock_txkz.return_value = kz_client
        self.store.kz_client = None

        parent = makeService(config)

        sd = defer.Deferred()
        get_supervisor().deferred_pool.add(sd)
        d = parent.stopService()

        self.assertNoResult(d)
        self.assertFalse(kz_client.stop.called)
        sd.callback(None)
        self.successResultOf(d)
        self.assertTrue(kz_client.stop.called)


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
