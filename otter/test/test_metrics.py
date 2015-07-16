"""
Tests for `metrics.py`
"""

import operator
from io import StringIO

from effect import Constant, Effect, base_dispatcher

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
from otter.cloud_client import TenantScope
from otter.constants import ServiceType
from otter.metrics import (
    GroupMetrics,
    MetricsService,
    Options,
    QUERY_GROUPS_OF_TENANTS,
    add_to_cloud_metrics,
    collect_metrics,
    get_all_metrics,
    get_all_metrics_effects,
    get_scaling_groups,
    get_specific_scaling_groups,
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
    resolve_effect,
)


class GetSpecificScalingGroupsTests(SynchronousTestCase):
    """Tests for :func:`get_specific_scaling_groups`."""

    def test_query(self):
        def _exec(query, params, c):
            return succeed(exec_args[(query, freeze(params))])
        client = mock.Mock(spec=CQLClient)
        rows = [
            {'created_at': '0', 'desired': 'some', 'status': 'ACTIVE'},
            {'desired': 'some', 'status': 'ACTIVE'},  # no created_at
            {'created_at': '0', 'status': 'ACTIVE'},  # no desired
            {'created_at': '0', 'desired': 'some'},   # no status
            {'created_at': '0', 'desired': 'some', 'status': 'DISABLED'},
            {'created_at': '0', 'desired': 'some', 'deleting': 'True', },
            {'created_at': '0', 'desired': 'some', 'status': 'ERROR'}]
        expected_query = QUERY_GROUPS_OF_TENANTS.format(tids="'foo', 'bar'")
        exec_args = {(expected_query, freeze({})): rows}

        client.execute.side_effect = _exec

        results = self.successResultOf(
            get_specific_scaling_groups(client, ['foo', 'bar']))
        self.assertEqual(list(results), [rows[0], rows[3]])


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

    def test_does_not_filter_on_desired(self):
        """
        If `with_null_desired=True` then groups with null desired are returned
        """
        groups = [{'tenantId': 1, 'groupId': 2,
                   'desired': 3, 'created_at': None},
                  {'tenantId': 1, 'groupId': 3,
                   'desired': None, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 5,
                   'desired': 3, 'created_at': 'c'}]
        self._add_exec_args(
            self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5,
                               with_null_desired=True)
        self.assertEqual(list(self.successResultOf(d)), groups[1:])

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
        servers = {
            'g1': [{'status': 'ACTIVE'}] * 3 + [{'status': 'BUILD'}] * 2}
        groups = [{'groupId': 'g1', 'desired': 3},
                  {'groupId': 'g2', 'desired': 4}]
        self.assertEqual(
            get_tenant_metrics('t', groups, servers),
            [GroupMetrics('t', 'g1', 3, 3, 2),
             GroupMetrics('t', 'g2', 4, 0, 0)])


def _server(group, state):
    return {'status': state,
            'metadata': {'rax:auto_scaling_group_id': group}}


class GetAllMetricsEffectsTests(SynchronousTestCase):
    """Tests for :func:`get_all_metrics_effects`"""

    def test_get_all_metrics(self):
        """
        Metrics are returned based on the requests done to get server info.
        """
        # Maybe this could use a parameterized "get_all_scaling_group_servers"
        # call to avoid needing to stub the nova responses, but it seems okay.
        servers_t1 = {
            'g1': ([_server('g1', 'ACTIVE')] * 3 +
                   [_server('g1', 'BUILD')] * 2),
            'g2': [_server('g2', 'ACTIVE')]}

        servers_t2 = {
            'g4': [_server('g4', 'ACTIVE'),
                   _server('g4', 'BUILD')]}

        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 3},
                  {'tenantId': 't1', 'groupId': 'g2', 'desired': 4},
                  {'tenantId': 't2', 'groupId': 'g4', 'desired': 2}]

        tenant_servers = {'t1': servers_t1, 't2': servers_t2}

        effs = get_all_metrics_effects(groups, mock_log())
        # All the effs are wrapped in TenantScopes to indicate the tenant
        # of ServiceRequests made under them. We use that tenant to get the
        # stubbed result of get_all_scaling_group_servers.
        results = [
            resolve_effect(eff, tenant_servers[eff.intent.tenant_id])
            for eff in effs]

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

        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 0},
                  {'tenantId': 't2', 'groupId': 'g2', 'desired': 0}]
        effs = get_all_metrics_effects(groups, log)
        results = []
        for eff in effs:
            if eff.intent.tenant_id == 't1':
                results.append(resolve_effect(eff, {}))
            elif eff.intent.tenant_id == 't2':
                err = (ZeroDivisionError, ZeroDivisionError('foo bar'), None)
                results.append(resolve_effect(eff, err, is_error=True))
        self.assertEqual(
            results,
            [None, [GroupMetrics('t1', 'g1', desired=0, actual=0, pending=0)]])
        log.err.assert_called_once_with(
            CheckFailureValue(ZeroDivisionError('foo bar')))


class GetAllMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_metrics`.
    """

    def test_get_all_metrics(self):
        """Gets group's metrics"""
        def _game(groups, logs, _print=False):
            return [Effect(Constant(['foo', 'bar'])),
                    Effect(Constant(['baz']))]
        d = get_all_metrics(base_dispatcher, object(),
                            get_all_metrics_effects=_game)
        self.assertEqual(set(self.successResultOf(d)),
                         set(['foo', 'bar', 'baz']))

    def test_ignore_error_results(self):
        """
        When get_all_metrics_effects returns a list containing a None, those
        elements are ignored.
        """
        def _game(groups, log, _print=False):
            return [Effect(Constant(None)),
                    Effect(Constant(['foo']))]
        d = get_all_metrics(base_dispatcher, object(),
                            get_all_metrics_effects=_game)
        self.assertEqual(self.successResultOf(d), ['foo'])


class AddToCloudMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`add_to_cloud_metrics`
    """

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
        log = object()

        eff = add_to_cloud_metrics(
            m['ttlInSeconds'], 'ord', td, ta, tp, log=log)

        req = eff.intent
        self.assertEqual(req.service_type, ServiceType.CLOUD_METRICS_INGEST)
        self.assertEqual(req.method, 'POST')
        self.assertEqual(req.url, 'ingest')
        self.assertEqual(req.data, req_data)
        self.assertEqual(req.log, log)


class CollectMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`collect_metrics`
    """

    def setUp(self):
        """
        mock dependent functions
        """
        self.connect_cass_servers = patch(
            self, 'otter.metrics.connect_cass_servers')
        self.client = mock.Mock(spec=['disconnect'])
        self.client.disconnect.return_value = succeed(None)
        self.connect_cass_servers.return_value = self.client

        self.groups = mock.Mock()
        self.get_specific_scaling_groups = patch(
            self, 'otter.metrics.get_specific_scaling_groups',
            return_value=succeed(self.groups))
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

        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'service': 'ms', 'tenant_id': 'tid',
                                   'region': 'IAD',
                                   'ttl': 200},
                       'region': 'r', 'cloudServersOpenStack': 'nova',
                       'cloudLoadBalancers': 'clb', 'rackconnect': 'rc'}

        self.dispatcher = base_dispatcher
        self.get_legacy_dispatcher = lambda r, auth, log, cfgs: self.dispatcher

    def _fake_perform(self, dispatcher, effect):
        """
        Assert that the only effect passed to this perform is the scoped
        result of add_to_cloud_metrics.
        """
        self.assertEqual(effect,
                         Effect(TenantScope(Effect(Constant(None)), 'tid')))

    def test_metrics_collected(self):
        """
        Metrics is collected after getting groups from cass and servers
        from nova and it is added to blueflood
        """
        _reactor = mock.Mock()
        d = collect_metrics(_reactor, self.config,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertIsNone(self.successResultOf(d))

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_scaling_groups.assert_called_once_with(
            self.client, props=['status'], group_pred=IsCallable())
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, _print=False)
        self.add_to_cloud_metrics.assert_called_once_with(
            self.config['metrics']['ttl'], 'r', 107, 26, 1,
            log=metrics_log)
        self.client.disconnect.assert_called_once_with()

    def test_metrics_collected_convergence_tenants(self):
        """
        Metrics is collected after getting groups from cass and servers
        from nova and it is added to blueflood
        """
        self.config['convergence-tenants'] = ['foo', 'bar']
        _reactor = mock.Mock()
        d = collect_metrics(_reactor, self.config,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertIsNone(self.successResultOf(d))

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_specific_scaling_groups.assert_called_once_with(
            self.client, tenant_ids=['foo', 'bar'])
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, _print=False)
        self.add_to_cloud_metrics.assert_called_once_with(
            self.config['metrics']['ttl'], 'r', 107, 26, 1,
            log=metrics_log)
        self.client.disconnect.assert_called_once_with()

    def test_with_client(self):
        """
        Uses client provided and does not disconnect it before returning
        """
        client = mock.Mock(spec=['disconnect'])
        d = collect_metrics(mock.Mock(), self.config, client=client,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertIsNone(self.successResultOf(d))
        self.assertFalse(self.connect_cass_servers.called)
        self.assertFalse(client.disconnect.called)

    def test_with_authenticator(self):
        """
        Uses authenticator provided instead of creating new
        """
        _reactor, auth = mock.Mock(), mock.Mock()
        d = collect_metrics(_reactor, self.config, authenticator=auth,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertIsNone(self.successResultOf(d))
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, _print=False)


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


class ServiceTests(SynchronousTestCase):
    """
    Tests for :func:`otter.metrics.makeService` and
    :class:`otter.metrics.MetricsService`
    """

    def setUp(self):
        """
        Mock cass connection and authenticator
        """
        self.client = mock.Mock(spec=['disconnect'])
        self.client.disconnect.return_value = succeed('disconnected')
        self.mock_ccs = patch(
            self, 'otter.metrics.connect_cass_servers',
            return_value=self.client)
        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'interval': 20}}
        self.mock_cm = patch(
            self, 'otter.metrics.collect_metrics', return_value=succeed(None))
        self.log = mock_log()
        self.clock = Clock()

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
