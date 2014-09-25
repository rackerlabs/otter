"""
Tests for `metrics.py`
"""

import mock

from pyrsistent import freeze

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.defer import succeed

from otter.metrics import (
    get_scaling_groups, get_tenant_metrics, get_all_metrics, GroupMetrics)
from otter.test.utils import patch

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
        self.select = 'SELECT "tenantId", "groupId", desired, active, pending FROM scaling_group '

    def _add_exec_args(self, query, params, ret):
        self.exec_args[freeze((query, params))] = ret

    def test_no_batch(self):
        """
        Gets all groups when total groups < batch size
        """
        groups = [{'tenantId': i, 'groupId': j, 'desired': 3}
                  for i in range(2) for j in range(2)]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, 5)
        self.assertEqual(self.successResultOf(d), {0: groups[:2], 1: groups[2:]})

    def test_filters_no_desired(self):
        """
        Does not include groups that do not have desired
        """
        groups = [{'tenantId': 1, 'groupId': 2, 'desired': None},
                  {'tenantId': 1, 'groupId': 2, 'desired': 4}]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups)
        d = get_scaling_groups(self.client, 5)
        self.assertEqual(self.successResultOf(d), {1: groups[1:]})

    def test_groups_more_batch(self):
        """
        Gets all groups of tenant even if they are more than batch size
        """
        groups = [{'tenantId': 1, 'groupId': i, 'desired': 3} for i in range(7)]
        self._add_exec_args(self.select + ' LIMIT :limit;', {'limit': 5}, groups[:5])
        self._add_exec_args(
            self.select + 'WHERE "tenantId"=:tenantId AND "groupId">:groupId LIMIT :limit;',
            {'limit': 5, 'tenantId': 1, 'groupId': 4}, groups[5:])
        self._add_exec_args(
            self.select + 'WHERE token("tenantId") > token(:tenantId) LIMIT :limit;',
            {'limit': 5, 'tenantId': 1}, [])
        d = get_scaling_groups(self.client, 5)
        self.assertEqual(self.successResultOf(d), {1: groups})

    def test_tenants_more_batch(self):
        """
        Gets tenants if they are tenant, groups are > batch size
        """
        groups1 = [{'tenantId': 1, 'groupId': i, 'desired': 3} for i in range(7)]
        groups2 = [{'tenantId': 2, 'groupId': i, 'desired': 4} for i in range(9)]
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
        d = get_scaling_groups(self.client, 5)
        self.assertEqual(self.successResultOf(d), {1: groups1, 2: groups2})


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
        groups = {'t1': [{'groupId': 'g1', 'desired': 3}, {'groupId': 'g2', 'desired': 4}],
                  't2': [{'groupId': 'g4', 'desired': 2}]}

        self.tenant_servers['t1'] = servers_t1
        self.tenant_servers['t2'] = servers_t2

        d = get_all_metrics(groups, 'a', 'n', 'r', clock='c')

        self.assertEqual(
            set(self.successResultOf(d)),
            set([GroupMetrics('t1', 'g1', 3, 3, 2), GroupMetrics('t1', 'g2', 4, 1, 0),
                 GroupMetrics('t2', 'g4', 2, 1, 1)]))
