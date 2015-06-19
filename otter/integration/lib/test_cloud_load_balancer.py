"""Tests for :mod:`otter.integration.lib.cloud_load_balancer`"""
import json

from testtools.matchers import Equals

from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer,
    ContainsAllIPs,
    ExcludesAllIPs,
    HasLength)
from otter.integration.lib.test_nova import Response, get_fake_treq
from otter.util.deferredutils import TimedOutError
from otter.util.http import APIError, headers


class _FakeRCS(object):
    endpoints = {'loadbalancers': 'clburl'}
    token = "token"


class CLBTests(SynchronousTestCase):
    """
    Tests for the :class:`CloudLoadBalancer` API calls.
    """
    def setUp(self):
        """
        Set up fake pool, treq, responses, and RCS.
        """
        self.pool = object()
        self.rcs = _FakeRCS()
        self.server_id = 'server_id'
        self.expected_kwargs = {
            'headers': headers('token'),
            'pool': self.pool
        }

    def get_clb(self, method, url, treq_args_kwargs, response, str_body):
        """
        Stub out treq, and return a cloud load balancer
        """
        clb = CloudLoadBalancer(
            pool=self.pool,
            treq=get_fake_treq(self, method, url, treq_args_kwargs,
                               (response, str_body)))
        clb.clb_id = 12345
        return clb

    def test_list_nodes(self):
        """
        Listing nodes calls the right endpoint and succeeds on 200.
        """
        clb = self.get_clb('get', 'clburl/loadbalancers/12345/nodes',
                           ((), self.expected_kwargs),
                           Response(200), '{"nodes": []}')
        d = clb.list_nodes(self.rcs)
        self.assertEqual({'nodes': []}, self.successResultOf(d))

    def test_update_node(self):
        """
        Update node calls the right endpoint and succeeds on 202.
        """
        clb = self.get_clb(
            'put', 'clburl/loadbalancers/12345/nodes/54321',
            (('{"node": {"weight": 5}}',), self.expected_kwargs),
            Response(202), '')
        d = clb.update_node(self.rcs, 54321, weight=5)
        self.assertEqual('', self.successResultOf(d))

    def test_delete_nodes_retries_until_success(self):
        """
        Deleting one or more nodes calls the right endpoint and succeeds on
        202.
        """
        clock = Clock()
        self.expected_kwargs['params'] = [("id", 11111), ("id", 22222)]
        main_treq_args = ['delete', 'clburl/loadbalancers/12345/nodes',
                          ((), self.expected_kwargs)]

        pending_update = {
            "message": ("Load Balancer '12345' has a status of "
                        "'PENDING_UPDATE' and is considered immutable."),
            "code": 422
        }

        clb = self.get_clb(
            *(main_treq_args + [Response(422), json.dumps(pending_update)]))

        d = clb.delete_nodes(self.rcs, (11111, 22222), clock=clock)
        self.assertNoResult(d)
        clock.pump([3])
        self.assertNoResult(d)

        clb.treq = get_fake_treq(
            *([self] + main_treq_args + [(Response(202), "")]))

        clock.pump([3])
        self.assertEqual(self.successResultOf(d), "")

    def test_delete_nodes_retries_until_timeout(self):
        """
        If the CLB is in PENDING_UPDATE state, retries executing the delete
        every 3 seconds until it times out at 60 seconds.
        """
        clock = Clock()
        pending_update = {
            "message": ("Load Balancer '12345' has a status of "
                        "'PENDING_UPDATE' and is considered immutable."),
            "code": 422
        }
        self.expected_kwargs['params'] = [("id", 11111), ("id", 22222)]
        clb = self.get_clb(
            'delete', 'clburl/loadbalancers/12345/nodes',
            ((), self.expected_kwargs),
            Response(422), json.dumps(pending_update))

        d = clb.delete_nodes(self.rcs, (11111, 22222), clock=clock)

        self.assertNoResult(d)
        clock.pump([3])
        self.assertNoResult(d)
        clock.pump([3] * 19)
        self.failureResultOf(d, TimedOutError)

    def test_delete_nodes_fails_on_non_422_PENDING_UDPATE(self):
        """
        If the CLB is in PENDING_UPDATE state, retries executing the delete
        every 3 seconds until it times out at 60 seconds.
        """
        clock = Clock()
        pending_update = {
            "message": ("Load Balancer '12345' has a status of "
                        "'PENDING_DELETE' and is considered immutable."),
            "code": 422
        }
        self.expected_kwargs['params'] = [("id", 11111), ("id", 22222)]
        clb = self.get_clb(
            'delete', 'clburl/loadbalancers/12345/nodes',
            ((), self.expected_kwargs),
            Response(422), json.dumps(pending_update))

        d = clb.delete_nodes(self.rcs, (11111, 22222), clock=clock)

        self.failureResultOf(d, APIError)


class WaitForNodesTestCase(SynchronousTestCase):
    """
    Tests for :func:`CloudLoadBalancer.wait_for_nodes`.
    """
    def setUp(self):
        """
        Set up fake pool, clock, treq, responses, and RCS.
        """
        self.pool = object()
        self.nodes = {'nodes': []}
        self.clock = Clock()
        self.get_calls = 0

        class FakeTreq(object):
            @classmethod
            def get(cls, url, headers, pool):
                self.get_calls += 1
                self.assertIs(self.pool, pool)
                self.assertEqual(["token"], headers.get('x-auth-token'))
                self.assertEqual(['clburl', 'loadbalancers', 'clb_id',
                                  'nodes'],
                                 url.split('/'))
                return succeed(Response(200))

            @classmethod
            def json_content(cls, resp):
                return succeed(self.nodes)

        self.rcs = _FakeRCS()
        self.clb = CloudLoadBalancer(pool=self.pool, treq=FakeTreq)
        self.clb.clb_id = 'clb_id'

    def test_retries_until_matcher_matches(self):
        """
        If the matcher does not matches the load balancer state, retries until
        it does.
        """
        d = self.clb.wait_for_nodes(
            self.rcs,
            Equals(['done']),
            timeout=5,
            period=1,
            clock=self.clock)
        self.clock.pump((1, 1, 1))
        self.assertNoResult(d)
        self.assertEqual(4, self.get_calls)

        self.nodes = {'nodes': ['done']}
        self.clock.pump([1])
        self.assertEqual(None, self.successResultOf(d))
        self.assertEqual(5, self.get_calls)

    def test_retries_until_timeout(self):
        """
        If the matcher does not matches the load balancer state, retries until
        it times out.
        """
        d = self.clb.wait_for_nodes(
            self.rcs,
            Equals(['done']),
            timeout=5,
            period=1,
            clock=self.clock)
        self.clock.pump((1, 1, 1, 1, 1))
        self.assertEqual(5, self.get_calls)
        self.failureResultOf(d, TimedOutError)


class MatcherTestCase(SynchronousTestCase):
    """
    Tests for the CLB matchers.
    """
    def test_contains_all_ips_success(self):
        """
        :class:`ContainsAllIPs` succeeds when the nodes contain all the IPs
        given.
        """
        matcher = ContainsAllIPs(['10.0.0.1', '10.0.0.2', '10.0.0.2'])
        mismatch = matcher.match([
            {'id': i, 'address': '10.0.0.{0}'.format(i)}
            for i in (1, 2)
        ])
        self.assertEqual(None, mismatch)

    def test_contains_all_ips_failure(self):
        """
        :class:`ContainsAllIPs` fail when the nodes contain only some or
        none of the all the IPs given.
        """
        matcher = ContainsAllIPs(['10.0.0.1', '10.0.0.2', '10.0.0.2'])
        self.assertNotEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 3)]),
            "Partial match succeeds when all should be required."
        )
        self.assertNotEqual(None, matcher.match([]), "No matches succed.")

    def test_excludes_all_ips_success(self):
        """
        :class:`ExcludesAllIPs` succeeds when the nodes do not contain any of
        the IPs given.
        """
        matcher = ExcludesAllIPs(['10.0.0.1', '10.0.0.1'])
        mismatch = matcher.match([
            {'id': i, 'address': '10.0.0.{0}'.format(i)}
            for i in (2, 3)
        ])
        self.assertEqual(None, mismatch)

    def test_excludes_all_ips_failure(self):
        """
        :class:`ExcludesAllIPs` fails when the nodes contain any or all of
        the IPs given.
        """
        matcher = ExcludesAllIPs(['10.0.0.1', '10.0.0.2'])
        self.assertNotEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 2)]),
            "Complete match succeeds when none should be present."
        )
        self.assertNotEqual(
            None,
            matcher.match([{'id': 1, 'address': '10.0.0.1'}]),
            "Partial match succeeds when none should be present."
        )

    def test_has_length(self):
        """
        :class:`HasLength` only succeeds when the number of nodes matches the
        length given.
        """
        matcher = HasLength(2)
        self.assertNotEqual(
            None,
            matcher.match([{'id': 1, 'address': '10.0.0.1'}])
        )
        self.assertNotEqual(None, matcher.match([]))
        self.assertEqual(
            None,
            matcher.match([{'id': i, 'address': '10.0.0.{0}'.format(i)}
                           for i in (1, 2)]))
