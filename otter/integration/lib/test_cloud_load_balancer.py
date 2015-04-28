"""Tests for :mod:`otter.integration.lib.cloud_load_balancer`"""
from testtools.matchers import Equals

from otter.util.deferredutils import TimedOutError
from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer,
    ContainsAllIPs,
    ExcludesAllIPs,
    HasLength)

from twisted.internet.defer import succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase


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

        class FakeRCS(object):
            endpoints = {'loadbalancers': 'clburl'}
            token = "token"

        class Resp(object):
            code = 200

        class FakeTreq(object):
            @classmethod
            def get(cls, url, headers, pool):
                self.get_calls += 1
                self.assertIs(self.pool, pool)
                self.assertEqual(["token"], headers.get('x-auth-token'))
                self.assertEqual(['clburl', 'loadbalancers', 'clb_id',
                                  'nodes'],
                                 url.split('/'))
                return succeed(Resp())

            @classmethod
            def json_content(cls, resp):
                return succeed(self.nodes)

        self.rcs = FakeRCS()
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
