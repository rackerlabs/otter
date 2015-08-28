"""
Tests for `metrics.py`
"""

import operator
from datetime import datetime
from io import StringIO

from effect import Constant, Effect, Func, base_dispatcher
from effect.testing import perform_sequence

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
    GetAllGroups,
    MetricsService,
    Options,
    QUERY_GROUPS_OF_TENANTS,
    add_to_cloud_metrics,
    collect_metrics,
    unchanged_divergent_groups,
    get_all_metrics,
    get_all_metrics_effects,
    get_scaling_groups,
    get_specific_scaling_groups,
    get_tenant_metrics,
    get_todays_tenants,
    get_todays_scaling_groups,
    makeService
)
from otter.test.test_auth import identity_config
from otter.test.utils import (
    CheckFailureValue,
    IsCallable,
    Provides,
    const,
    matches,
    mock_log,
    noop,
    patch,
    resolve_effect,
)
from otter.util.fileio import ReadFileLines, WriteFileLines


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
        def _game(groups, log, _print=False):
            self.assertEqual(log, "log")
            return [Effect(Constant(['foo', 'bar'])),
                    Effect(Constant(['baz']))]
        d = get_all_metrics(base_dispatcher, object(), "log",
                            get_all_metrics_effects=_game)
        self.assertEqual(set(self.successResultOf(d)),
                         set(['foo', 'bar', 'baz']))

    def test_ignore_error_results(self):
        """
        When get_all_metrics_effects returns a list containing a None, those
        elements are ignored.
        """
        def _game(groups, log, _print=False):
            self.assertEqual(log, "log")
            return [Effect(Constant(None)),
                    Effect(Constant(['foo']))]
        d = get_all_metrics(base_dispatcher, object(), "log",
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


class UnchangedDivergentGroupsTests(SynchronousTestCase):
    """
    Tests for :func:`unchanged_divergent_groups`
    """

    def setUp(self):
        self.clock = Clock()

    def invoke(self, current={}, metrics=[]):
        return unchanged_divergent_groups(self.clock, current, 3600, metrics)

    def test_no_groups(self):
        """
        There are no group metrics collected
        """
        groups, logs = self.invoke()
        self.assertEqual(groups, {})
        self.assertEqual(logs, [])

    def test_converged(self):
        """
        All converged groups are popped out from divergent_groups
        """
        dg = {('t1', 'g1'): (2, 23), ('t1', 'g2'): (3, 67)}
        metrics = [GroupMetrics("t1", "g1", 1, 1, 0),
                   GroupMetrics("t1", "g2", 2, 0, 2)]
        groups, logs = self.invoke(dg, metrics)
        self.assertEqual(groups, {})
        self.assertEqual(logs, [])

    def test_diverged(self):
        """
        - Changed groups are removed from tracking
        - tracks new groups
        - Timeout groups are logged including long timeouts
        - Existing diverged groups not yet timed out are not logged
        """
        metrics = [GroupMetrics("t1", "cg", 1, 1, 1),
                   GroupMetrics("t2", "tg", 2, 1, 2),  # timeout
                   GroupMetrics("t2", "tg2", 5, 2, 1),  # high timeout
                   GroupMetrics("t1", "fine", 2, 0, 2),
                   GroupMetrics("t1", "ng", 3, 1, 1),  # new group
                   GroupMetrics("t1", "dg", 6, 0, 3)]
        dg = {
            ("t1", "cg"): (0, 23),  # changed group: any value diff from hash
            ("t2", "tg"): (3600, hash((2, 1, 2))),  # timeout group
            ("t2", "tg2"): (0, hash((5, 2, 1))),  # high timeout group
            ("t1", "dg"): (7100, hash((6, 0, 3))),  # diverged but not timeout
            ("t2", "delg"): (4000, hash((4, 1, 2)))  # deleted group
        }
        self.clock.advance(7203)
        groups, logs = self.invoke(dg, metrics)
        # changed group "cg" removed and converged group "fine" not added
        # Deleted group "delg" removed
        self.assertEqual(
            groups,
            {("t2", "tg"): (3600, hash((2, 1, 2))),  # timeout group remains
             ("t2", "tg2"): (0, hash((5, 2, 1))),  # high timeout group remains
             ("t1", "ng"): (7203, hash((3, 1, 1))),  # new group added
             ("t1", "dg"): (7100, hash((6, 0, 3)))})  # diverged group remains
        # timeout groups to be logged. Notice that already diverged but not
        # timedout groups ("t1, "dg") are not to be logged
        self.assertEqual(
            logs,
            [(metrics[1], 3603), (metrics[2], 7203)])


class GetTodaysTenants(SynchronousTestCase):
    """
    Tests for :func:`get_todays_tenants`
    """

    def setUp(self):
        self.tenants = range(10)
        self.today = datetime(1970, 1, 2)

    def test_last_none(self):
        """
        returns first 5 sorted tenants with length 5 and todays date
        """
        self.assertEqual(
            get_todays_tenants(self.tenants, self.today, None, None),
            (self.tenants[:5], 5, self.today))

    def test_same_day(self):
        """
        returns same tenants as last time if asked within same day
        """
        last_date = self.today.replace(hour=13, minute=20)
        self.assertEqual(
            get_todays_tenants(self.tenants, self.today, 3, last_date),
            (self.tenants[:3], 3, self.today))

    def test_next_day(self):
        """
        returns tenants with 5 more for next day
        """
        prev_day = datetime(1970, 1, 1)
        self.assertEqual(
            get_todays_tenants(self.tenants, self.today, 3, prev_day),
            (self.tenants[:8], 8, self.today))

    def test_all(self):
        """
        returns all tenants for new day if < 5 tenants are remaining since
        last time
        """
        prev_day = datetime(1970, 1, 1)
        self.assertEqual(
            get_todays_tenants(self.tenants, self.today, 7, prev_day),
            (self.tenants, 10, self.today))

    def test_previous_day(self):
        """
        Same as `test_same_day`
        """
        next_day = datetime(1970, 1, 3)
        self.assertEqual(
            get_todays_tenants(self.tenants, self.today, 3, next_day),
            (self.tenants[:3], 3, self.today))


class GetTodaysScalingGroupsTests(SynchronousTestCase):
    """
    Tests for :func:`get_todays_scaling_groups`
    """

    def test_success(self):
        groups = (
            [{"tenantId": "t1", "a": "1"}, {"tenantId": "t1", "a": "2"}] +
            [{"tenantId": "t{}".format(i), "b": str(i)} for i in range(2, 10)])
        seq = [
            (GetAllGroups(), const(groups)),
            (ReadFileLines("file"), const(["2", "0.0"])),
            (Func(datetime.utcnow), const(datetime(1970, 1, 2))),
            (WriteFileLines("file", ["7", "86400.0"]), noop)
        ]
        r = perform_sequence(seq, get_todays_scaling_groups(["t1"], "file"))
        self.assertEqual(set(freeze(r)), set(freeze(groups[:9])))



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
        self.log = mock_log()

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
        d = collect_metrics(_reactor, self.config, self.log,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertEqual(self.successResultOf(d), self.metrics)

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_scaling_groups.assert_called_once_with(
            self.client, props=['status'], group_pred=IsCallable())
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, self.log, _print=False)
        self.add_to_cloud_metrics.assert_called_once_with(
            self.config['metrics']['ttl'], 'r', 107, 26, 1, log=self.log)
        self.client.disconnect.assert_called_once_with()

    def test_metrics_collected_convergence_tenants(self):
        """
        Metrics is collected after getting groups of convergence tenants only
        from cass and servers of those tenants from nova and it is added to
        blueflood
        """
        self.config['convergence-tenants'] = ['foo', 'bar']
        _reactor = mock.Mock()
        d = collect_metrics(_reactor, self.config, self.log,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertEqual(self.successResultOf(d), self.metrics)

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_specific_scaling_groups.assert_called_once_with(
            self.client, tenant_ids=['foo', 'bar'])
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, self.log, _print=False)
        self.add_to_cloud_metrics.assert_called_once_with(
            self.config['metrics']['ttl'], 'r', 107, 26, 1,
            log=self.log)
        self.client.disconnect.assert_called_once_with()

    def test_with_client(self):
        """
        Uses client provided and does not disconnect it before returning
        """
        client = mock.Mock(spec=['disconnect'])
        d = collect_metrics(mock.Mock(), self.config, self.log, client=client,
                            perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertEqual(self.successResultOf(d), self.metrics)
        self.assertFalse(self.connect_cass_servers.called)
        self.assertFalse(client.disconnect.called)

    def test_with_authenticator(self):
        """
        Uses authenticator provided instead of creating new
        """
        _reactor, auth = mock.Mock(), mock.Mock()
        d = collect_metrics(_reactor, self.config, self.log,
                            authenticator=auth, perform=self._fake_perform,
                            get_legacy_dispatcher=self.get_legacy_dispatcher)
        self.assertEqual(self.successResultOf(d), self.metrics)
        self.get_all_metrics.assert_called_once_with(
            self.dispatcher, self.groups, self.log, _print=False)


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
        self.mock_cm = patch(
            self, 'otter.metrics.collect_metrics', return_value=succeed(None))
        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'interval': 20}}
        self.log = mock_log()
        self.clock = Clock()

    def _service(self):
        self.collect = mock.Mock()
        return MetricsService('r', self.config, self.log, self.clock,
                              collect=self.collect)

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

    def test_collect_called_again(self):
        """
        `self.collect` is called again based on interval given in config
        """
        s = self._service()
        s.startService()
        self.assertTrue(s.running)
        self.collect.assert_called_once_with(
            'r', self.config, self.log, client=self.client,
            authenticator=matches(Provides(IAuthenticator)))
        self.clock.advance(20)
        self.assertEqual(len(self.collect.mock_calls), 2)
        self.collect.assert_called_with(
            'r', self.config, self.log, client=self.client,
            authenticator=matches(Provides(IAuthenticator)))

    @mock.patch("otter.metrics.unchanged_divergent_groups")
    def test_collect(self, mock_udg):
        """
        `self.collect` gets metrics from collect_metrics and logs unchanged
        diverged groups got from `unchanged_divergent_groups`
        """
        self.mock_cm.return_value = succeed("metrics")
        s = self._service()
        s._divergent_groups = "dg"
        mock_udg.return_value = (
            "ndg",
            [(GroupMetrics("t", "g1", 2, 0, 1), 3600),
             (GroupMetrics("t", "g2", 3, 1, 0), 7200)])
        d = s.collect('r', self.config, client="client")
        self.assertIsNone(self.successResultOf(d))
        self.mock_cm.assert_called_once_with('r', self.config, client="client")
        mock_udg.assert_called_once_with("r", "dg", 3600, "metrics")
        self.log.err.assert_has_calls([
            mock.call(mock.ANY,
                      ("Group {group_id} of {tenant_id} remains diverged "
                       "and unchanged for {divergent_time}"),
                      tenant_id="t", group_id="g1", desired=2, actual=0,
                      pending=1, divergent_time="1:00:00"),
            mock.call(mock.ANY,
                      ("Group {group_id} of {tenant_id} remains diverged "
                       "and unchanged for {divergent_time}"),
                      tenant_id="t", group_id="g2", desired=3, actual=1,
                      pending=0, divergent_time="2:00:00")
        ])
        self.assertEqual(s._divergent_groups, "ndg")

    def test_collect_error(self):
        """
        `self.collect` logs error and returns success if `collect_metrics`
        errors
        """
        s = self._service()
        self.mock_cm.return_value = fail(ValueError('a'))
        d = s.collect('r', self.config, client="client")
        self.assertIsNone(self.successResultOf(d))
        self.log.err.assert_called_once_with(None, "Error collecting metrics")

    def test_stop_service(self):
        """
        Client is disconnected when service is stopped
        """
        s = self._service()
        s.startService()
        self.assertTrue(s.running)
        self.assertEqual(len(self.collect.mock_calls), 1)
        d = s.stopService()
        self.assertEqual(self.successResultOf(d), 'disconnected')
        self.assertFalse(s.running)
        # self.collect is not called again
        self.clock.advance(20)
        self.assertEqual(len(self.collect.mock_calls), 1)
