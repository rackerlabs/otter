"""
Tests for the otter-api tap plugin.
"""

import json
from copy import deepcopy

import mock

from testtools.matchers import Contains, IsInstance

from twisted.application.service import MultiService
from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import CachingAuthenticator, SingleTenantAuthenticator
from otter.constants import (
    CONVERGENCE_DIRTY_DIR, ServiceType, get_service_configs)
from otter.convergence.service import Converger
from otter.models.cass import CassScalingGroupCollection as OriginalStore
from otter.supervisor import SupervisorService, get_supervisor, set_supervisor
from otter.tap.api import (
    HealthChecker,
    Options,
    call_after_supervisor,
    makeService,
    setup_converger,
    setup_scheduler
)
from otter.test.test_auth import identity_config
from otter.test.test_effect_dispatcher import full_intents
from otter.test.utils import CheckFailure, matches, patch
from otter.util.config import set_config_data
from otter.util.deferredutils import DeferredPool
from otter.util.zkpartitioner import Partitioner


test_config = {
    'port': 'tcp:9999',
    'admin': 'tcp:9789',
    'cassandra': {
        'seed_hosts': ['tcp:127.0.0.1:9160'],
        'keyspace': 'otter_test',
        'timeout': 10
    },
    'environment': 'prod',
    'region': 'ord',
    'identity': identity_config,
    'cloudServersOpenStack': 'cloudServersOpenStack',
    'cloudLoadBalancers': 'cloudLoadBalancers',
    'rackconnect': 'rackconnect',
    'metrics': {'service': 'cloudMetricsIngest',
                'region': 'IAD'},
    'limits': {'absolute': {'maxGroups': 100}}
}


class APIOptionsTests(SynchronousTestCase):
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


class HealthCheckerTests(SynchronousTestCase):
    """
    Tests for the HealthChecker object
    """
    def setUp(self):
        """
        Sample clock
        """
        self.clock = Clock()

    def test_no_checks(self):
        """
        If there are no checks, HealthChecker returns healthy
        """
        checker = HealthChecker(self.clock)
        d = checker.health_check()
        self.assertEqual(self.successResultOf(d), {'healthy': True})

    def test_invalid_check(self):
        """
        If an invalid check is added, its health is unhealthy
        """
        checker = HealthChecker(self.clock, {'invalid': None})
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
        checker = HealthChecker(
            self.clock,
            {'fail': mock.Mock(side_effect=Exception)})
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
        checker = HealthChecker(
            self.clock,
            {'sync': mock.Mock(return_value=(True, {}))})
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
            self.clock,
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
        checker = HealthChecker(self.clock, {
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
        checker = HealthChecker(self.clock, dict([
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

    def test_check_is_timed_out(self):
        """
        Each health check is timed out after 15 seconds
        """
        checker = HealthChecker(
            self.clock,
            {'a': mock.Mock(return_value=defer.Deferred()),
             'b': mock.Mock(return_value=defer.succeed((True, {})))})
        d = checker.health_check()
        self.assertNoResult(d)
        self.clock.advance(16)
        r = self.successResultOf(d)
        self.assertEqual(r, {
            'healthy': False,
            'a': {'healthy': False, 'details': {'reason': mock.ANY}},
            'b': {'healthy': True, 'details': {}}
        })
        self.assertIn('a health check timed out', r['a']['details']['reason'])


class CallAfterSupervisorTests(SynchronousTestCase):
    """
    Tests for `call_after_supervisor`
    """

    def test_calls_after_supervisor_finishes(self):
        """
        Func is called after supervisor is completed stopped
        """
        supervisor = mock.Mock(spec=['deferred_pool'])
        supervisor.deferred_pool = mock.Mock(spec=DeferredPool)
        supervisor.deferred_pool.notify_when_empty.return_value = \
            defer.Deferred()
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


class APIMakeServiceTests(SynchronousTestCase):
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

        self.RoundRobinCassandraCluster = patch(
            self, 'otter.tap.api.RoundRobinCassandraCluster')
        self.LoggingCQLClient = patch(
            self, 'otter.tap.api.LoggingCQLClient')
        self.TimingOutCQLClient = patch(
            self, 'otter.tap.api.TimingOutCQLClient')
        self.log = patch(self, 'otter.tap.api.log')

        Otter_patcher = mock.patch('otter.tap.api.Otter')
        self.Otter = Otter_patcher.start()
        self.addCleanup(Otter_patcher.stop)

        self.reactor = patch(self, 'otter.tap.api.reactor')

        def scaling_group_collection(*args, **kwargs):
            self.store = OriginalStore(*args, **kwargs)
            return self.store

        patch(self, 'otter.tap.api.CassScalingGroupCollection',
              wraps=scaling_group_collection)

        self.health_checker = None

        def make_health_checker(*args, **kwargs):
            self.health_checker = HealthChecker(*args, **kwargs)
            return self.health_checker

        patch(self, 'otter.tap.api.HealthChecker',
              side_effect=make_health_checker)

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
        self.assertTrue('tcp:9789' not in
                        [args[0] for args, _ in self.service.call_args_list])

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
        self.service.return_value.setServiceParent.assert_called_with(
            expected_parent)

    def test_cassandra_seed_hosts_endpoints(self):
        """
        makeService will create a client endpoint for each address in the
        cassandra seed_hosts.
        """
        makeService(test_config)
        self.clientFromString.assert_called_once_with(
            self.reactor, 'tcp:127.0.0.1:9160')

    def test_unicode_cassandra_seed_hosts_endpoints(self):
        """
        makeService will create a client endpoint for each address in the
        cassandra seed_hosts with a byte endpoint string even if config was
        given in unicode
        """
        unicode_config = json.loads(json.dumps(test_config, encoding="utf-8"))
        makeService(unicode_config)
        self.clientFromString.assert_called_once_with(
            self.reactor, 'tcp:127.0.0.1:9160')
        self.assertTrue(isinstance(self.clientFromString.call_args[0][1], str))

    def test_cassandra_cluster_with_endpoints_and_keyspace(self):
        """
        makeService configures a RoundRobinCassandraCluster with the
        seed_endpoints and the keyspace from the config.
        """
        makeService(test_config)
        self.RoundRobinCassandraCluster.assert_called_once_with(
            [self.clientFromString.return_value],
            'otter_test', disconnect_on_cancel=True)

    def test_cassandra_scaling_group_collection_with_cluster(self):
        """
        makeService configures a CassScalingGroupCollection with the
        cassandra cluster connection.
        """
        makeService(test_config)
        self.log.bind.assert_called_once_with(system='otter.silverberg')
        self.TimingOutCQLClient.assert_called_once_with(
            self.reactor,
            self.RoundRobinCassandraCluster.return_value,
            10)
        self.LoggingCQLClient.assert_called_once_with(
            self.TimingOutCQLClient.return_value,
            self.log.bind.return_value)

        self.assertEqual(self.store.connection,
                         self.LoggingCQLClient.return_value)
        self.assertEqual(self.store.reactor, self.reactor)

    def test_cassandra_cluster_disconnects_on_stop(self):
        """
        Cassandra cluster connection is disconnected when main service is
        stopped
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
        self.Otter.assert_called_once_with(self.store, 'ord',
                                           self.health_checker.health_check)

    def test_max_groups(self):
        """
        CassScalingGroupCollection is created with max groups taken from
        config
        """
        makeService(test_config)
        self.assertEqual(self.store.max_groups, 100)

    @mock.patch('otter.tap.api.reactor')
    @mock.patch('otter.tap.api.generate_authenticator')
    @mock.patch('otter.tap.api.SupervisorService', wraps=SupervisorService)
    def test_authenticator(self, mock_ss, mock_ga, mock_reactor):
        """
        Authenticator is generated and passed to SupervisorService
        """
        self.addCleanup(lambda: set_supervisor(None))
        makeService(test_config)
        mock_ga.assert_called_once_with(mock_reactor, test_config['identity'])
        self.assertIdentical(get_supervisor().authenticator,
                             mock_ga.return_value)

    @mock.patch('otter.tap.api.SupervisorService', wraps=SupervisorService)
    def test_health_checker_no_zookeeper(self, supervisor):
        """
        A health checker is constructed by default with the store and kazoo
        health check
        """
        self.addCleanup(lambda: set_supervisor(None))
        self.assertIsNone(self.health_checker)
        makeService(test_config)
        self.assertIsNotNone(self.health_checker)
        self.assertEqual(self.health_checker.checks['store'],
                         self.store.health_check)
        self.assertEqual(self.health_checker.checks['kazoo'],
                         self.store.kazoo_health_check)
        self.assertEqual(self.health_checker.checks['supervisor'],
                         get_supervisor().health_check)

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

    @mock.patch('otter.tap.api.addObserver')
    @mock.patch('otter.tap.api.get_cf_observer')
    def test_cloudfeeds_setup(self, mock_getobserver, mock_addobserver):
        """
        Cloud feeds observer is setup if it is there in config
        """
        conf = deepcopy(test_config)
        conf['cloudfeeds'] = {'service': 'cloudFeeds', 'tenant_id': 'tid',
                              'url': 'url'}
        makeService(conf)
        serv_confs = get_service_configs(conf)
        serv_confs[ServiceType.CLOUD_FEEDS] = {
            'name': 'cloudFeeds', 'region': 'ord', 'url': 'url'}
        mock_getobserver.assert_called_once_with(
            self.reactor, matches(IsInstance(CachingAuthenticator)), 'tid',
            'ord', serv_confs)
        mock_addobserver.assert_called_once_with(mock_getobserver.return_value)

        # single tenant authenticator is created
        real_auth = mock_getobserver.call_args[0][1]
        self.assertIsInstance(
            real_auth._authenticator._authenticator._authenticator,
            SingleTenantAuthenticator)

    @mock.patch('otter.tap.api.get_cf_observer')
    def test_cloudfeeds_no_setup(self, mock_getobserver):
        """
        Cloud feeds observer is not setup if it is not there in config
        """
        makeService(test_config)
        self.assertFalse(mock_getobserver.called)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    @mock.patch('otter.tap.api.KazooClient')
    @mock.patch('otter.tap.api.ThreadPool')
    @mock.patch('otter.tap.api.TxLogger')
    def test_kazoo_client_success(self, mock_tx_logger, mock_thread_pool,
                                  mock_kazoo_client, mock_txkz,
                                  mock_setup_scheduler):
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
        thread_pool = mock.Mock()
        mock_thread_pool.return_value = thread_pool
        logger = mock.Mock()
        mock_tx_logger.return_value = logger
        kazoo_client = mock.Mock()
        mock_kazoo_client.return_value = kazoo_client

        parent = makeService(config)

        self.log.bind.assert_called_with(system='kazoo')
        mock_txkz.assert_called_once_with(
            self.reactor, thread_pool, kazoo_client)
        mock_kazoo_client.assert_called_once_with(
            hosts='zk_hosts',
            connection_retry=dict(max_tries=-1, max_delay=600),
            logger=logger)
        mock_tx_logger.assert_called_once_with(self.log.bind.return_value)
        mock_thread_pool.assert_called_once_with(maxthreads=20)
        kz_client.start.assert_called_once_with(timeout=None)

        # setup_scheduler and store.kz_client is not called yet, and nothing
        # added to the health checker
        self.assertFalse(mock_setup_scheduler.called)
        self.assertIsNone(self.store.kz_client)

        # they are called after start completes
        start_d.callback(None)
        mock_setup_scheduler.assert_called_once_with(
            parent, self.store, kz_client)
        self.assertEqual(self.store.kz_client, kz_client)
        sch = mock_setup_scheduler.return_value
        self.assertEqual(self.health_checker.checks['scheduler'],
                         sch.health_check)
        self.assertEqual(self.Otter.return_value.scheduler, sch)

        # Check for no logs case also
        mock_txkz.reset_mock()
        config['zookeeper']['no_logs'] = True
        parent = makeService(config)
        mock_txkz.assert_called_once_with(
            self.reactor, thread_pool, kazoo_client)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    @mock.patch('otter.tap.api.KazooClient')
    @mock.patch('otter.tap.api.ThreadPool')
    @mock.patch('otter.tap.api.TxLogger')
    def test_kazoo_client_failed(self, mock_tx_logger, mock_thread_pool,
                                 mock_kazoo_client, mock_txkz,
                                 mock_setup_scheduler):
        """
        `setup_scheduler` is not called if TxKazooClient is not able to start
        Error is logged
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.fail(ValueError('e'))
        mock_txkz.return_value = kz_client
        thread_pool = mock.Mock()
        mock_thread_pool.return_value = thread_pool
        logger = mock.Mock()
        mock_tx_logger.return_value = logger
        kazoo_client = mock.Mock()
        mock_kazoo_client.return_value = kazoo_client

        makeService(config)

        mock_txkz.assert_called_once_with(
            self.reactor, thread_pool, kazoo_client)
        kz_client.start.assert_called_once_with(timeout=None)
        self.assertFalse(mock_setup_scheduler.called)
        self.log.err.assert_called_once_with(CheckFailure(ValueError),
                                             'Could not start TxKazooClient')

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    @mock.patch('otter.tap.api.setup_converger')
    def test_kazoo_client_stops(self,
                                mock_setup_converger,
                                mock_txkz,
                                mock_setup_scheduler):
        """
        TxKazooClient is stopped when parent service stops
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.succeed(None)
        mock_txkz.return_value = kz_client

        parent = makeService(config)

        kz_client.stop.return_value = defer.Deferred()
        d = parent.stopService()

        self.assertTrue(kz_client.stop.called)
        self.assertNoResult(d)
        kz_client.stop.return_value.callback(None)
        self.successResultOf(d)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    @mock.patch('otter.tap.api.setup_converger')
    def test_kazoo_client_stops_after_supervisor(self,
                                                 mock_setup_converger,
                                                 mock_txkz,
                                                 mock_setup_scheduler):
        """
        Kazoo is stopped after supervisor stops
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.succeed(None)
        kz_client.stop.return_value = defer.succeed(None)
        mock_txkz.return_value = kz_client

        parent = makeService(config)

        sd = defer.Deferred()
        get_supervisor().deferred_pool.add(sd)
        d = parent.stopService()

        self.assertNoResult(d)
        self.assertFalse(kz_client.stop.called)
        sd.callback(None)
        self.successResultOf(d)
        self.assertTrue(kz_client.stop.called)

    @mock.patch('otter.tap.api.setup_scheduler')
    @mock.patch('otter.tap.api.TxKazooClient')
    @mock.patch('otter.tap.api.setup_converger')
    def test_converger_dispatcher(self, mock_setup_converger,
                                  mock_txkz, mock_setup_scheduler):
        """
        The converger dispatcher that is set up after kazoo is ready can handle
        all intents.
        """
        config = test_config.copy()
        config['zookeeper'] = {'hosts': 'zk_hosts', 'threads': 20}
        kz_client = mock.Mock(spec=['start', 'stop'])
        kz_client.start.return_value = defer.succeed(None)
        mock_txkz.return_value = kz_client

        parent = makeService(config)

        mock_setup_converger.assert_called_once_with(
            parent, kz_client, mock.ANY, 10, 3600)

        dispatcher = mock_setup_converger.call_args[0][2]

        # Check dispatcher is set in otter object
        self.assertIs(self.Otter.return_value.dispatcher, dispatcher)

        for intent in full_intents():
            self.assertIsNot(dispatcher(intent), None)


class ConvergerSetupTests(SynchronousTestCase):
    """Tests for :func:`setup_converger`."""

    @mock.patch('otter.tap.api.watch_children')
    def test_setup_converger(self, mock_watch_children):
        """
        Puts a :obj:`Converger` with a :obj:`Partitioner` in the given parent
        service.
        """
        ms = MultiService()
        kz_client = object()
        dispatcher = object()
        interval = 50
        setup_converger(ms, kz_client, dispatcher, interval, build_timeout=35)
        [converger] = ms.services
        self.assertIs(converger.__class__, Converger)
        self.assertEqual(converger.build_timeout, 35)
        self.assertEqual(converger._dispatcher, dispatcher)
        [partitioner] = converger.services
        [timer] = partitioner.services
        self.assertIs(partitioner.__class__, Partitioner)
        self.assertIs(partitioner, converger.partitioner)
        self.assertIs(partitioner.kz_client, kz_client)
        self.assertEqual(timer.step, interval)
        mock_watch_children.assert_called_once_with(
            kz_client, CONVERGENCE_DIRTY_DIR, converger.divergent_changed)


class SchedulerSetupTests(SynchronousTestCase):
    """
    Tests for `setup_scheduler`
    """

    def setUp(self):
        """
        Mock args
        """
        self.config = {
            'scheduler': {
                'buckets': 10,
                'partition': {'path': '/part_path', 'time_boundary': 15},
                'batchsize': 100,
                'interval': 10
            }
        }
        set_config_data(self.config)
        self.parent = MultiService()
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
        svc = setup_scheduler(self.parent, self.store, self.kz_client)
        buckets = range(1, 11)
        self.store.set_scheduler_buckets.assert_called_once_with(buckets)
        self.assertEqual(self.parent.services, [svc])
        self.assertEqual(svc.store, self.store)
        self.assertEqual(svc.partitioner.buckets, buckets)
        self.assertEqual(svc.partitioner.kz_client, self.kz_client)
        self.assertEqual(svc.partitioner.partitioner_path, '/part_path')

    def test_mock_store_with_scheduler(self):
        """
        SchedulerService is not created with mock store
        """
        self.config['mock'] = True
        set_config_data(self.config)
        self.assertIs(
            setup_scheduler(self.parent, self.store, self.kz_client),
            None)
        self.assertFalse(self.store.set_scheduler_buckets.called)
