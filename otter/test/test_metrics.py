"""
Tests for `metrics.py`
"""

import operator
import time
from io import StringIO

from effect import Constant, Effect, Func, base_dispatcher
from effect.testing import SequenceDispatcher, perform_sequence

import mock

from testtools.matchers import IsInstance

from toolz.dicttoolz import merge

from twisted.internet.base import ReactorBase
from twisted.internet.defer import fail, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import IAuthenticator
from otter.cloud_client import TenantScope, service_request
from otter.constants import ServiceType
from otter.metrics import (
    GetAllGroups,
    GroupMetrics,
    MetricsService,
    Options,
    add_to_cloud_metrics,
    collect_metrics,
    get_all_metrics,
    get_all_metrics_effects,
    get_tenant_metrics,
    makeService,
    unchanged_divergent_groups
)
from otter.test.convergence.test_model import sample_servers
from otter.test.test_auth import identity_config
from otter.test.utils import (
    CheckFailureValue,
    Provides,
    const,
    intent_func,
    matches,
    mock_log,
    nested_sequence,
    noop,
    patch,
    resolve_effect,
    set_config_for_test
)


class GetTenantMetricsTests(SynchronousTestCase):
    """Tests for :func:`get_tenant_metrics`"""

    def test_get_tenant_metrics(self):
        """Extracts metrics from the servers."""
        servers = {
            'g1': ([_server('g1', 'ACTIVE')] * 3 +
                   [_server('g1', 'BUILD')] * 2 +
                   [_server("g1", "ERROR"), _server("g1", "DELETED"),
                    _server("g1", "SHUTOFF"), _server("g1", "PASSWORD")]),
            'g3': [_server("g3", 'ACTIVE')]
        }
        groups = [{'groupId': 'g1', 'desired': 3},
                  {'groupId': 'g2', 'desired': 4}]
        self.assertEqual(
            set(get_tenant_metrics('t', groups, servers)),
            # g1 2 BUILD and 1 PASSWORD servers is considered pending
            set([GroupMetrics('t', 'g1', 3, 3, 3),
                 GroupMetrics('t', 'g2', 4, 0, 0),
                 GroupMetrics('t', 'g3', 0, 1, 0)])
        )


def _server(group, state):
    server = sample_servers()[0]
    return merge(
        server,
        {'status': state,
         'metadata': {'rax:auto_scaling_group_id': group}})


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

        groups = {
            "t1": [{'tenantId': 't1', 'groupId': 'g1', 'desired': 3},
                   {'tenantId': 't1', 'groupId': 'g2', 'desired': 4}],
            "t2": [{'tenantId': 't2', 'groupId': 'g4', 'desired': 2}]}

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

        groups = {
            "t1": [{'tenantId': 't1', 'groupId': 'g1', 'desired': 0}],
            "t2": [{'tenantId': 't2', 'groupId': 'g2', 'desired': 0}]}
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

    def test_added(self):
        """
        total desired, pending and actual are added to cloud metrics
        """
        metrics = [GroupMetrics('t1', 'g1', 3, 2, 0),
                   GroupMetrics('t2', 'g1', 4, 4, 1),
                   GroupMetrics('t2', 'g', 100, 20, 0),
                   GroupMetrics('t3', 'g3', 5, 3, 0)]
        config = {"non-convergence-tenants": ["t1"]}
        m = {'collectionTime': 100000, 'ttlInSeconds': 5 * 24 * 60 * 60}
        md = merge(m, {'metricValue': 112, 'metricName': 'ord.desired'})
        ma = merge(m, {'metricValue': 29, 'metricName': 'ord.actual'})
        mp = merge(m, {'metricValue': 1, 'metricName': 'ord.pending'})
        mt = merge(m, {'metricValue': 3, 'metricName': 'ord.tenants'})
        mg = merge(m, {'metricValue': 4, 'metricName': 'ord.groups'})
        mt1d = merge(m, {'metricValue': 3, 'metricName': 'ord.t1.desired'})
        mt1a = merge(m, {'metricValue': 2, 'metricName': 'ord.t1.actual'})
        mt1p = merge(m, {'metricValue': 0, 'metricName': 'ord.t1.pending'})
        mt2d = merge(m, {'metricValue': 104, 'metricName': 'ord.t2.desired'})
        mt2a = merge(m, {'metricValue': 24, 'metricName': 'ord.t2.actual'})
        mt2p = merge(m, {'metricValue': 1, 'metricName': 'ord.t2.pending'})
        mt3d = merge(m, {'metricValue': 5, 'metricName': 'ord.t3.desired'})
        mt3a = merge(m, {'metricValue': 3, 'metricName': 'ord.t3.actual'})
        mt3p = merge(m, {'metricValue': 0, 'metricName': 'ord.t3.pending'})
        cd = merge(m, {'metricValue': 109, 'metricName': 'ord.conv_desired'})
        ca = merge(m, {'metricValue': 27, 'metricName': 'ord.conv_actual'})
        cdiv = merge(m, {'metricValue': 82,
                         'metricName': 'ord.conv_divergence'})

        req_data = [md, ma, mp, mt, mg, mt1d, mt1a, mt1p, mt2d, mt2a, mt2p,
                    mt3d, mt3a, mt3p, cd, ca, cdiv]
        log = mock_log()
        seq = [
            (Func(time.time), const(100)),
            (service_request(
                ServiceType.CLOUD_METRICS_INGEST, "POST", "ingest",
                data=req_data, log=log).intent, noop)
        ]
        eff = add_to_cloud_metrics(m['ttlInSeconds'], 'ord', metrics, 3,
                                   config, log)
        self.assertIsNone(perform_sequence(seq, eff))
        log.msg.assert_called_once_with(
            'total desired: {td}, total_actual: {ta}, total pending: {tp}',
            td=112, ta=29, tp=1)


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

        self.log = mock_log()

        self.get_all_metrics = patch(self, 'otter.metrics.get_all_metrics',
                                     return_value=succeed("metrics"))
        self.groups = {"t": "t1group", "t2": "2 groups"}

        self.add_to_cloud_metrics = patch(
            self, 'otter.metrics.add_to_cloud_metrics',
            side_effect=intent_func("atcm"))

        self.config = {'cassandra': 'c', 'identity': identity_config,
                       'metrics': {'service': 'ms', 'tenant_id': 'tid',
                                   'region': 'IAD',
                                   'ttl': 200, "last_tenant_fpath": "lpath"},
                       'region': 'r', 'cloudServersOpenStack': 'nova',
                       'cloudLoadBalancers': 'clb',
                       'cloudOrchestration': 'orch',
                       'rackconnect': 'rc',
                       "convergence-tenants": ["ct"]}

        self.sequence = SequenceDispatcher([
            (GetAllGroups(), const(self.groups)),
            (TenantScope(mock.ANY, "tid"),
             nested_sequence([
                 (("atcm", 200, "r", "metrics", 2, self.config,
                   self.log, False), noop)
             ]))
        ])
        self.get_dispatcher = patch(self, "otter.metrics.get_dispatcher",
                                    return_value=self.sequence)

    def test_metrics_collected(self):
        """
        Metrics is collected after getting groups from cass and servers
        from nova and it is added to blueflood
        """
        _reactor = mock.Mock()

        with self.sequence.consume():
            d = collect_metrics(_reactor, self.config, self.log)
            self.assertEqual(self.successResultOf(d), "metrics")

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_all_metrics.assert_called_once_with(
            self.get_dispatcher.return_value, self.groups, self.log,
            _print=False)
        self.client.disconnect.assert_called_once_with()

    def test_with_client(self):
        """
        Uses client provided and does not disconnect it before returning
        """
        client = mock.Mock(spec=['disconnect'])
        with self.sequence.consume():
            d = collect_metrics("reactr", self.config, self.log, client=client)
            self.assertEqual(self.successResultOf(d), "metrics")
        self.assertFalse(self.connect_cass_servers.called)
        self.assertFalse(client.disconnect.called)

    def test_with_authenticator(self):
        """
        Uses authenticator provided instead of creating new
        """
        _reactor, auth = mock.Mock(), mock.Mock()
        with self.sequence.consume():
            d = collect_metrics(_reactor, self.config, self.log,
                                authenticator=auth)
            self.assertEqual(self.successResultOf(d), "metrics")
        self.get_dispatcher.assert_called_once_with(
            _reactor, auth, self.log, mock.ANY, mock.ANY)

    def test_without_metrics(self):
        """
        Doesnt add metrics to blueflood if metrics config is not there
        """
        sequence = SequenceDispatcher([
            (GetAllGroups(), const(self.groups))
        ])
        self.get_dispatcher.return_value = sequence
        del self.config["metrics"]
        with sequence.consume():
            d = collect_metrics("reactor", self.config, self.log)
            self.assertEqual(self.successResultOf(d), "metrics")
        self.assertFalse(self.add_to_cloud_metrics.called)


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
