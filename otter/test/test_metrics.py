"""
Tests for `metrics.py`
"""

import mock
import json

from pyrsistent import freeze

from toolz.dicttoolz import merge

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed

from otter.metrics import (
    get_scaling_groups, get_tenant_metrics, get_all_metrics, GroupMetrics,
    add_to_cloud_metrics, main as metrics_main)
from otter.test.utils import patch, StubTreq2, matches
from otter.util.http import headers
from otter.log import BoundLog

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
        self.select = ('SELECT "groupId","tenantId",active,created_at,desired,pending '
                       'FROM scaling_group ')

    def _add_exec_args(self, query, params, ret):
        self.exec_args[freeze((query, params))] = ret

    def test_all_groups_less_than_batch(self):
        """
        Works when number of all groups of all tenants < batch size
        """
        groups = [{'tenantId': i, 'groupId': j, 'desired': 3, 'created_at': 'c'}
                  for i in range(2) for j in range(2)]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_filters_no_created_or_desired(self):
        """
        Does not include groups that do not have created_at or desired
        """
        groups = [{'tenantId': 1, 'groupId': 2, 'desired': 3, 'created_at': None},
                  {'tenantId': 1, 'groupId': 3, 'desired': None, 'created_at': 'c'},
                  {'tenantId': 1, 'groupId': 4, 'desired': None, 'created_at': None},
                  {'tenantId': 1, 'groupId': 5, 'desired': 3, 'created_at': 'c'}]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups[-1:])

    def test_last_tenant_has_less_groups(self):
        """
        Fetches initial batch, then gets all groups of last tenant in that batch
        and stops when there are no more tenants
        """
        groups = [{'tenantId': 1, 'groupId': i, 'desired': 3, 'created_at': 'c'}
                  for i in range(7)]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups[:5])
        self._add_exec_args(
            self.select + 'WHERE "tenantId"=:tenantId AND "groupId">:groupId LIMIT :limit;',
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups[5:])
        self._add_exec_args(
            self.select + 'WHERE token("tenantId") > token(:tenantId) LIMIT :limit;',
            {'limit': 5, 'tenantId': 1}, [])
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups)

    def test_many_tenants_having_more_than_batch_groups(self):
        """
        Gets all groups when there are many tenants each of them having groups > batch size
        """
        groups1 = [{'tenantId': 1, 'groupId': i, 'desired': 3, 'created_at': 'c'}
                   for i in range(7)]
        groups2 = [{'tenantId': 2, 'groupId': i, 'desired': 4, 'created_at': 'c'}
                   for i in range(9)]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups1[:5])
        self._add_exec_args(
            self.select + 'WHERE "tenantId"=:tenantId AND "groupId">:groupId LIMIT :limit;',
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups1[5:])
        self._add_exec_args(
            self.select + 'WHERE token("tenantId") > token(:tenantId) LIMIT :limit;',
            {'limit': 5, 'tenantId': 1}, groups2[:5])
        self._add_exec_args(
            self.select + 'WHERE "tenantId"=:tenantId AND "groupId">:groupId LIMIT :limit;',
            {'limit': 5, 'tenantId': 2, 'groupId': 4}, groups2[5:])
        self._add_exec_args(
            self.select + 'WHERE token("tenantId") > token(:tenantId) LIMIT :limit;',
            {'limit': 5, 'tenantId': 2}, [])
        d = get_scaling_groups(self.client, batch_size=5)
        self.assertEqual(list(self.successResultOf(d)), groups1 + groups2)


class GetMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`get_tenant_metrics` and :func:`get_all_metrics`
    """

    def setUp(self):
        """
        Mock get_scaling_group_servers
        """
        self.tenant_servers = {}
        self.mock_gsgs = patch(
            self, 'otter.metrics.get_scaling_group_servers',
            side_effect=lambda t, *a, **k: succeed(self.tenant_servers[t]))

    def test_get_tenant_metrics(self):
        """
        Gets group's metrics
        """
        servers = {'g1': [{'status': 'ACTIVE'}] * 3 + [{'status': 'BUILD'}] * 2}
        groups = [{'groupId': 'g1', 'desired': 3}, {'groupId': 'g2', 'desired': 4}]
        self.assertEqual(
            get_tenant_metrics('t', groups, servers),
            [GroupMetrics('t', 'g1', 3, 3, 2), GroupMetrics('t', 'g2', 4, 0, 0)])

    def test_get_all_metrics(self):
        """
        Gets group's metrics
        """
        servers_t1 = {'g1': [{'status': 'ACTIVE'}] * 3 + [{'status': 'BUILD'}] * 2,
                      'g2': [{'status': 'ACTIVE'}]}
        servers_t2 = {'g4': [{'status': 'ACTIVE'}, {'status': 'BUILD'}]}
        groups = [{'tenantId': 't1', 'groupId': 'g1', 'desired': 3},
                  {'tenantId': 't1', 'groupId': 'g2', 'desired': 4},
                  {'tenantId': 't2', 'groupId': 'g4', 'desired': 2}]

        self.tenant_servers['t1'] = servers_t1
        self.tenant_servers['t2'] = servers_t2

        d = get_all_metrics(groups, 'a', 'n', 'r', clock='c')

        self.assertEqual(
            set(self.successResultOf(d)),
            set([GroupMetrics('t1', 'g1', 3, 3, 2), GroupMetrics('t1', 'g2', 4, 1, 0),
                 GroupMetrics('t2', 'g4', 2, 1, 1)]))


class AddToCloudMetricsTests(SynchronousTestCase):
    """
    Tests for :func:`add_to_cloud_metrics`
    """

    def setUp(self):
        """
        Setup treq
        """
        self.resp = {
            'access': {
                'token': {'id': 'token'},
                'serviceCatalog': [
                    {'endpoints': [{"region": "IAD", "publicURL": "url"}],
                     "name": "cloudMetricsIngest"}
                ]
            }
        }
        self.au = patch(self, 'otter.metrics.authenticate_user',
                        return_value=succeed(self.resp))

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
        req = ('POST', 'url/ingest', {'headers': headers('token'),
                                      'data': json.dumps([md, ma, mp])})
        treq = StubTreq2([(req, (200, ''))])
        conf = {'username': 'a', 'password': 'p', 'service': 'cloudMetricsIngest',
                'region': 'IAD', 'ttl': m['ttlInSeconds']}

        d = add_to_cloud_metrics(conf, 'idurl', 'ord', td, ta, tp, _treq=treq)

        self.assertIsNone(self.successResultOf(d))
        self.au.assert_called_once_with('idurl', 'a', 'p', log=matches(IsInstance(BoundLog)))


class MainTests(SynchronousTestCase):
    """
    Tests for :func:`main`
    """

    def setUp(self):
        """
        mock dependent functions
        """
        self.connect_cass_servers = patch(self, 'otter.metrics.connect_cass_servers')
        self.get_authenticator = patch(self, 'otter.metrics.get_authenticator')
        self.get_scaling_groups = patch(self, 'otter.metrics.get_scaling_groups')
        self.get_all_metrics = patch(self, 'otter.metrics.get_all_metrics')
        self.add_to_cloud_metrics = patch(self, 'otter.metrics.add_to_cloud_metrics')

    def test_metrics_collected(self):
        """
        Metrics is collected after getting groups from cass and servers from nova
        and it is added to blueflood
        """
        client = mock.Mock(spec=['disconnect'])
        client.disconnect.return_value = succeed(None)
        self.connect_cass_servers.return_value = client

        auth = mock.Mock()
        self.get_authenticator.return_value = auth

        groups = mock.Mock()
        self.get_scaling_groups.return_value = succeed(groups)

        metrics = [GroupMetrics('t', 'g1', 3, 2, 0), GroupMetrics('t2', 'g1', 4, 4, 1),
                   GroupMetrics('t2', 'g', 100, 20, 0)]
        self.get_all_metrics.return_value = succeed(metrics)

        _reactor = mock.Mock()
        config = {'cassandra': 'c', 'identity': {'url': 'id'}, 'metrics': 'm',
                  'region': 'r', 'services': {'nova': 'cloudServersOpenStack'}}

        d = metrics_main(_reactor, config)
        self.assertIsNone(self.successResultOf(d))

        self.connect_cass_servers.assert_called_once_with(_reactor, 'c')
        self.get_authenticator.assert_called_once_with(_reactor, {'url': 'id'})
        self.get_scaling_groups.assert_called_once_with(client)
        self.get_all_metrics.assert_called_once_with(
            groups, auth, 'cloudServersOpenStack', 'r', clock=_reactor, _print=False)
        self.add_to_cloud_metrics.assert_called_once_with(
            'm', 'id', 'r', 107, 26, 1)
        client.disconnect.assert_called_once_with()
