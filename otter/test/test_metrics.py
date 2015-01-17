"""
Tests for `metrics.py`
"""

import operator
from io import StringIO

from effect import Constant, Effect, Error
from effect.testing import Stub

import mock

from pyrsistent import freeze

from silverberg.client import CQLClient

from testtools.matchers import IsInstance

from toolz.dicttoolz import merge

from twisted.internet.base import ReactorBase
from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import IAuthenticator
from otter.constants import ServiceType, get_service_mapping
from otter.metrics import (
    GroupMetrics,
    MetricsService,
    Options,
    add_to_cloud_metrics,
    collect_metrics,
    get_all_metrics,
    get_all_metrics_effects,
    get_scaling_groups,
    get_tenant_metrics,
    makeService,
    metrics_log,
)
from otter.test.test_auth import identity_config
from otter.test.utils import (
    CheckFailure,
    CheckFailureValue,
    IsCallable,
    Provides,
    matches,
    mock_log,
    patch,
    resolve_retry_stubs,
    resolve_stubs,
)

from testtools.matchers import IsInstance

from silverberg.client import CQLClient


class GetScalingGroupsTests(SynchronousTestCase):
    """
    Tests for :func:`get_scaling_groups`
    """

    def setUp(self):
        """
        Mock
        """
        self.client = mock.Mock(spec=CQLClient)
        self.exec_args = {}

        def _exec(query, params, c):
            return succeed(self.exec_args[freeze((query, params))])

        self.client.execute.side_effect = _exec
        self.select = ('SELECT "groupId","tenantId",'
                       'active,created_at,desired,pending '
                       'FROM scaling_group ')

    def _add_exec_args(self, query, params, ret):
        self.exec_args[freeze((query, params))] = ret

    def test_all_groups_less_than_batch(self):
        """
        Works when number of all groups of all tenants < batch size
        """
        groups = [{'tenantId': i, 'groupId': j,
                   'desired': 3, 'created_at': 'c'}
                  for i in range(2) for j in range(2)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_filters_no_created_or_desired(self):
        """
        Does not include groups that do not have created_at or desired
        """
        groups = [{'tenantId': 1, 'groupId': 2,
                   'desired': 3, 'created_at': None},
                  {'tenantId': 1, 'groupId': 3,
                   'desired': None, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 4,
                   'desired': None, 'created_at': None},
                  {'tenantId': 1, 'groupId': 5,
                   'desired': 3, 'created_at': 'c'}]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups[-1:])

    def test_filters_on_group_pred_arg(self):
        """
        If group_pred arg is given then returns groups for which
        group_pred returns True
        """
        groups = [{'tenantId': 1, 'groupId': 2,
                   'desired': 3, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 3,
                   'desired': 2, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 4,
                   'desired': 6, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 5,
                   'desired': 4, 'created_at': 'c'}]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5,
                               group_pred=lambda g: g['desired'] % 3 == 0)
        self.assertEqual(list(self.successResultOf(d)),
                         [groups[0], groups[2]])

    def test_gets_props(self):
        """
        If props arg is given then returns groups with that property in it
        """
        groups = [{'tenantId': 1, 'groupId': 2, 'desired': 3,
                   'created_at': 'c', 'launch': 'l'},
                  {'tenantId': 1, 'groupId': 3, 'desired': 2,
                   'created_at': 'c', 'launch': 'b'}]
        self._add_exec_args(
            ('SELECT "groupId","tenantId",active,created_at,'
             'desired,launch,pending '
             'FROM scaling_group  LIMIT :limit;'),
            {'limit': 5}, groups)
        d = get_scaling_groups(self.client, props=['launch'], batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_last_tenant_has_less_groups(self):
        """
        Fetches initial batch, then gets all groups of last tenant
        in that batch and stops when there are no more tenants
        """
        groups = [{'tenantId': 1, 'groupId': i,
                   'desired': 3, 'created_at': 'c'}
                  for i in range(7)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups[:5])
        self._add_exec_args(
            self.select + ('WHERE "tenantId"=:tenantId AND '
                           '"groupId">:groupId LIMIT :limit;'),
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups[5:])
        self._add_exec_args(
            self.select + ('WHERE token("tenantId") > token(:tenantId)'
                           ' LIMIT :limit;'),
            {'limit': 5, 'tenantId': 1}, [])
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_many_tenants_having_more_than_batch_groups(self):
        """
        Gets all groups when there are many tenants each of them
        having groups > batch size
        """
        groups1 = [{'tenantId': 1, 'groupId': i,
                    'desired': 3, 'created_at': 'c'}
                   for i in range(7)]
        groups2 = [{'tenantId': 2, 'groupId': i,
                    'desired': 4, 'created_at': 'c'}
                   for i in range(9)]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups1[:5])
        where_tenant = ('WHERE "tenantId"=:tenantId AND '
                        '"groupId">:groupId LIMIT :limit;')
        where_token = ('WHERE token("tenantId") > token(:tenantId) '
                       'LIMIT :limit;')
        self._add_exec_args(
            self.select + where_tenant,
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups1[5:])
        self._add_exec_args(
            self.select + where_token,
            {'limit': 5, 'tenantId': 1}, groups2[:5])
        self._add_exec_args(
            self.select + where_tenant,
            {'limit': 5, 'tenantId': 2, 'groupId': 4}, groups2[5:])
        self._add_exec_args(
            self.select + where_token,
            {'limit': 5, 'tenantId': 2}, [])
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups1 + groups2)


class GetTenantMetricsTests(SynchronousTestCase):
    """Tests for :func:`get_tenant_metrics`"""

    def test_get_tenant_metrics(self):
        """Extracts metrics from the servers."""
        servers = {'g1': [{'status': 'ACTIVE'}] * 3 +
                         [{'status': 'BUILD'}] * 2}
        groups = [{'groupId': 'g1', 'desired': 3},
                  {'groupId': 'g2', 'desired': 4}]
        self.assertEqual(
            get_tenant_metrics('t', groups, servers),
            [GroupMetrics('t', 'g1', 3, 3, 2),
             GroupMetrics('t', 'g2', 4, 0, 0)])


class GetAllMetricsEffectsTests(SynchronousTestCase):
    """Tests for :func:`get_all_metrics_effects`"""

    def _server(self, group, state):
        return {'status': state,
                'metadata': {'rax:auto_scaling_group_id': group}}

    def test_get_all_metrics(self):
        """
        Metrics are returned based on the requests done to get server info.
        """
        # Maybe this could use a parameterized "get_scaling_group_servers" call
        # to avoid needing to stub the nova responses, but it seems okay.
        servers_t1 = {
            'servers': (
                [self._server('g1', 'ACTIVE')] * 3
                + [self._server('g1', 'BUILD')] * 2
                + [self._server('g2', 'ACTIVE')])}

        servers_t2 = {
            'servers': [self._server('g4', 'ACTIVE'),
                        self._server('g4', 'BUILD')]}

        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 3},
                  {'tenantId': 't1', 'groupId': 'g2', 'desired': 4},
                  {'tenantId': 't2', 'groupId': 'g4', 'desired': 2}]

        tenant_servers = {'t1': servers_t1, 't2': servers_t2}

        def get_bound_request_func(tenant_id):
            def request_func(service_type, method, url, headers=None,
                             data=None):
                return Effect(Stub(Constant(tenant_servers[tenant_id])))
            return request_func
        effs = get_all_metrics_effects(groups, get_bound_request_func,
                                       mock_log())

        # All of the HTTP requests are wrapped in retries, so unwrap them
        results = map(resolve_retry_stubs, effs)

        self.assertEqual(
            set(reduce(operator.add, results)),
            set([GroupMetrics('t1', 'g1', desired=3, actual=3, pending=2),
                 GroupMetrics('t1', 'g2', desired=4, actual=1, pending=0),
                 GroupMetrics('t2', 'g4', desired=2, actual=1, pending=1)]))

    def test_error_per_tenant(self):
        """
        When a request for servers fails, the associated effect results in
        None, and an error is logged.
        """
        log = mock_log()
        log.err.return_value = None

        def get_bound_request_func(tenant_id):
            def request_func(service_type, method, url, headers=None,
                             data=None):
                if tenant_id == 't1':
                    return Effect(Stub(Constant({'servers': []})))
                else:
                    return Effect(Stub(Error(ZeroDivisionError('foo bar'))))
            return request_func

        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 0},
                  {'tenantId': 't2', 'groupId': 'g2', 'desired': 0}]

        effs = get_all_metrics_effects(groups, get_bound_request_func, log)
        results = map(resolve_retry_stubs, effs)
        self.assertEqual(
            results,
            [None, [GroupMetrics('t1', 'g1', desired=0, actual=0, pending=0)]])
        log.err.assert_called_once_with(
            CheckFailureValue(ZeroDivisionError('foo bar')))


class GnarlyGetMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_metrics`.

    These tests aren't very nice -- they should eventually disappear, once more
    code is converted to using effects, and we don't need as much mocking.
    """

    def setUp(self):
        """Mock get_scaling_group_servers and get_request_func."""
        self.tenant_servers = {}
        # This is pretty nasty.

        # get_request_func is being mocked to just return the tenant id,
        # instead of a function. Nothing will call it, so it works.
        # Then, get_scaling_group_servers is being mocked to expect the tenant
        # ID instead of a request function, to use it to look up the server
        # data to return.
        self.mock_get_request_func = patch(
            self, 'otter.metrics.get_request_func',
            side_effect=lambda a, tenant_id, *args, **kwargs: tenant_id)
        self.mock_gsgs = patch(
            self, 'otter.metrics.get_scaling_group_servers',
            side_effect=lambda rf, server_predicate: (
                Effect(Constant(self.tenant_servers[rf]))))
        self.service_mapping = {ServiceType.CLOUD_SERVERS: 'nova'}

    def test_get_all_metrics(self):
        """
        Gets group's metrics
        """
        servers_t1 = {'g1': [{'status': 'ACTIVE'}] * 3 +
                            [{'status': 'BUILD'}] * 2,
                      'g2': [{'status': 'ACTIVE'}]}
        servers_t2 = {'g4': [{'status': 'ACTIVE'}, {'status': 'BUILD'}]}
        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 3},
                  {'tenantId': 't1', 'groupId': 'g2', 'desired': 4},
                  {'tenantId': 't2', 'groupId': 'g4', 'desired': 2}]

        self.tenant_servers['t1'] = servers_t1
        self.tenant_servers['t2'] = servers_t2

        authenticator = mock.Mock()

        d = get_all_metrics(groups, authenticator, self.service_mapping, 'r',
                            clock='c')

        self.assertEqual(
            set(self.successResultOf(d)),
            set([GroupMetrics('t1', 'g1', 3, 3, 2),
                 GroupMetrics('t1', 'g2', 4, 1, 0),
                 GroupMetrics('t2', 'g4', 2, 1, 1)]))
        self.mock_gsgs.assert_any_call('t1', server_predicate=IsCallable())
        self.mock_gsgs.assert_any_call('t2', server_predicate=IsCallable())

        self.mock_get_request_func.assert_any_call(
            authenticator, 't1', metrics_log, self.service_mapping, 'r')
        self.mock_get_request_func.assert_any_call(
            authenticator, 't2', metrics_log, self.service_mapping, 'r')

    def test_ignore_error_results(self):
        """
        When get_all_metrics_effects returns a list containing a None, those
        elements are ignored.
        """
        def mock_game(cass_groups, get_request_func_for_tenant, log,
                      _print=False):
            return [Effect(Constant(None)),
                    Effect(Constant([GroupMetrics('t1', 'g1', 0, 0, 0)]))]
        mock_game = patch(self, 'otter.metrics.get_all_metrics_effects',
                          side_effect=mock_game)
        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 0},
                  {'tenantId': 't2', 'groupId': 'g2', 'desired': 500}]
        authenticator = mock.Mock()
        d = get_all_metrics(groups, authenticator, self.service_mapping, 'r',
                            clock='c')
        self.assertEqual(
            self.successResultOf(d),
            [GroupMetrics('t1', 'g1', 0, 0, 0)])


class AddToCloudMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`add_to_cloud_metrics`
    """

    def setUp(self):
        """
        Setup treq
        """
        def request(*a, **k):
            self.a, self.k = a, k
            return Effect(Stub(Constant('r')))

        self.request = request

    @mock.patch('otter.metrics.time')
    def test_added(self, mock_time):
        """
        total desired, pending and actual are added to cloud metrics
        """
        td = 10
        ta = 20
        tp = 3
        mock_time.time.return_value = 100
        m = {'collectionTime': 100000, 'ttlInSeconds': 5 * 24 * 60 * 60}
        md = merge(m, {'metricValue': td, 'metricName': 'ord.desired'})
        ma = merge(m, {'metricValue': ta, 'metricName': 'ord.actual'})
        mp = merge(m, {'metricValue': tp, 'metricName': 'ord.pending'})
        req_data = [md, ma, mp]
        conf = {'ttl': m['ttlInSeconds']}
        log = object()

        eff = add_to_cloud_metrics(
            self.request, conf, 'ord', td, ta, tp, log=log)

        self.assertEqual(resolve_stubs(eff), 'r')
        self.assertEqual(
            self.a, (ServiceType.CLOUD_METRICS_INGEST, 'POST', 'ingest'))
        self.assertEqual(self.k, dict(data=req_data, log=log))


class CommonMocks(SynchronousTestCase):
    """
    Common mocks including :func:`connect_cass_servers` and
    :func:`generate_authenticator`
    """

    def setUp(self):
        """
        mock common stuff
        """
        self.connect_cass_servers = patch(
            self, 'otter.metrics.connect_cass_servers')
        self.client = mock.Mock(spec=['disconnect'])
        self.client.disconnect.return_value = succeed('disconnected')
        self.connect_cass_servers.return_value = self.client

        self.authenticator = object()
        self.mock_ga = patch(self, 'otter.metrics.generate_authenticator',
                             return_value=self.authenticator)


class CollectMetricsTests(CommonMocks):
    """
    Tests for :func:`collect_metrics`
    """

    def setUp(self):
        """
        mock dependent functions
        """
        super(CollectMetricsTests, self).setUp()
        self.groups = mock.Mock()
        self.get_scaling_groups = patch(
            self, 'otter.metrics.get_scaling_groups',
            return_value=succeed(self.groups))

        self.metrics = [GroupMetrics('t', 'g1', 3, 2, 0),
                        GroupMetrics('t2', 'g1', 4, 4, 1),
                        GroupMetrics('t2', 'g', 100, 20, 0)]
        self.get_all_metrics = patch(self, 'otter.metrics.get_all_metrics',
                                     return_value=succeed(self.metrics))

        self.add_to_cloud_metrics = patch(self,
                                          'otter.metrics.add_to_cloud_metrics',
                                          return_value=Effect(Constant(None)))
        self.req_func = object()
        self.mock_grf = patch(self, 'otter.metrics.get_request_func',
                              return_value=self.req_func)

        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'service': 'ms', 'tenant_id': 'tid',
                                   'region': 'IAD'},
                       'region': 'r', 'cloudServersOpenStack': 'nova',
                       'cloudLoadBalancers': 'clb', 'rackconnect': 'rc'}

    def test_metrics_collected(self):
        """
        Metrics is collected after getting groups from cass and servers
        from nova and it is added to blueflood
        """
        _reactor = mock.Mock()
        service_mapping = get_service_mapping(self.config)

        d = collect_metrics(_reactor, self.config)
        self.assertIsNone(self.successResultOf(d))

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_scaling_groups.assert_called_once_with(
            self.client, props=['status'], group_pred=IsCallable())
        self.get_all_metrics.assert_called_once_with(
            self.groups, self.authenticator, service_mapping,
            'r', clock=_reactor, _print=False)
        self.mock_grf.assert_called_once_with(
            self.authenticator, 'tid', metrics_log, service_mapping, 'IAD')
        self.add_to_cloud_metrics.assert_called_once_with(
            self.req_func, self.config['metrics'], 'r', 107, 26, 1,
            log=metrics_log)
        self.client.disconnect.assert_called_once_with()

    def test_with_client(self):
        """
        Uses client provided and does not disconnect it before returning
        """
        client = mock.Mock(spec=['disconnect'])
        d = collect_metrics(mock.Mock(), self.config, client=client)
        self.assertIsNone(self.successResultOf(d))
        self.assertFalse(self.connect_cass_servers.called)
        self.assertFalse(client.disconnect.called)

    def test_with_authenticator(self):
        """
        Uses authenticator provided instead of creating new
        """
        _reactor, auth = mock.Mock(), mock.Mock()
        d = collect_metrics(_reactor, self.config, authenticator=auth)
        self.assertIsNone(self.successResultOf(d))
        self.get_all_metrics.assert_called_once_with(
            self.groups, auth, get_service_mapping(self.config),
            'r', clock=_reactor, _print=False)


class APIOptionsTests(SynchronousTestCase):
    """
    Test the various command line options.
    """

    def test_config_options(self):
        """
        File given in --config option is parsed and its contents are
        added to `Options` object
        """
        config = Options()
        config.open = mock.Mock(return_value=StringIO(u'{"a": "b"}'))
        config.parseOptions(['--config=file.json'])
        self.assertEqual(config, {'a': 'b', 'config': 'file.json'})


class ServiceTests(CommonMocks):
    """
    Tests for :func:`otter.metrics.makeService` and
    :class:`otter.metrics.MetricsService`
    """

    def setUp(self):
        """
        Mock cass connection and authenticator
        """
        super(ServiceTests, self).setUp()
        self.mock_ccs = patch(
            self, 'otter.metrics.connect_cass_servers',
            return_value=self.client)
        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'interval': 20}}
        self.mock_cm = patch(
            self, 'otter.metrics.collect_metrics', return_value=succeed(None))

    def _service(self):
        return MetricsService('r', self.config, self.log, self.clock)

    def _cm_called(self, calls):
        self.assertEqual(len(self.mock_cm.mock_calls), calls)
        self.mock_cm.assert_called_with(
            'r', self.config, client=self.client,
            authenticator=matches(Provides(IAuthenticator)))

    @mock.patch('otter.metrics.MetricsService')
    def test_make_service(self, mock_ms):
        """
        MetricsService is returned with config
        """
        c = {'a': 'v'}
        s = makeService(c)
        self.assertIs(s, mock_ms.return_value)
        from otter.metrics import metrics_log
        mock_ms.assert_called_once_with(
            matches(IsInstance(ReactorBase)), c, metrics_log)

    def test_collect_metrics_called_again(self):
        """
        `collect_metrics` is called again based on interval given in config
        """
        s = self._service()
        s.startService()
        self.assertTrue(s.running)
        self._cm_called(1)
        self.clock.advance(20)
        self._cm_called(2)

    def test_collect_metrics_called_again_on_error(self):
        """
        `collect_metrics` is called again even if one of the
        previous call fails
        """
        s = self._service()
        self.mock_cm.return_value = fail(ValueError('a'))
        s.startService()
        self._cm_called(1)
        self.log.err.assert_called_once_with(CheckFailure(ValueError))
        # Service is still running
        self.assertTrue(s.running)
        # And collect_metrics is called again after interval is passed
        self.clock.advance(20)
        self._cm_called(2)

    def test_stop_service(self):
        """
        Client is disconnected when service is stopped
        """
        s = self._service()
        s.startService()
        self.assertTrue(s.running)
        self._cm_called(1)
        d = s.stopService()
        self.assertEqual(self.successResultOf(d), 'disconnected')
        self.assertFalse(s.running)
        # collect_metrics is not called again
        self.clock.advance(20)
        self._cm_called(1)
