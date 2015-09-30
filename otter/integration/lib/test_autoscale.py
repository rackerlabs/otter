"""Autoscale utility tests."""

from __future__ import print_function

from characteristic import attributes

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.autoscale import (
    ExcludesServers, HasActive, ScalingGroup)

from otter.util.deferredutils import TimedOutError


class WaitForStateTestCase(SynchronousTestCase):
    empty_group_state = {
        "group": {
            "paused": False,
            "pendingCapacity": 0,
            "name": "blah",
            "active": [],
            "activeCapacity": 0,
            "desiredCapacity": 0,
        }
    }

    group_state_w_2_servers = {
        "group": {
            "paused": False,
            "pendingCapacity": 0,
            "name": "blah",
            "active": ["hello", "world"],
            "activeCapacity": 2,
            "desiredCapacity": 0,
        }
    }

    def setUp(self):
        """Create our simulated clock and scaling group.  We link the group
        to the clock, giving us explicit (and, for the purposes of our test,
        synchronous) control over the scaling group's concept of elapsed time.
        """

        self.clock = Clock()
        self.sg = ScalingGroup(group_config={}, pool=None, reactor=self.clock)
        self.counter = 0

    def get_scaling_group_state_happy(self, rcs, success_codes=None):
        """This method implements a synchronous simulation of what we'd expect
        to see over the wire on an HTTP API transaction.  This method replaces
        the actual ScalingGroup method on instances.  (See setUp for an example
        of how this method is used.)

        This version emulates completion after a period of time.
        """
        self.assertEquals(success_codes, [200])
        if self.counter == self.threshold:
            return defer.succeed((200, self.group_state_w_2_servers))
        else:
            self.counter = self.counter + 1
            return defer.succeed((200, self.empty_group_state))

    def get_scaling_group_state_timeout(self, rcs, success_codes=None):
        """This method implements a synchronous simulation of what we'd expect
        to see over the wire on an HTTP API transaction.  This method replaces
        the actual ScalingGroup method on instances.  (See setUp for an example
        of how this method is used.)

        This version never yields the desired number of servers.
        """
        self.assertEquals(success_codes, [200])
        return defer.succeed((200, self.empty_group_state))

    def test_poll_until_happy(self):
        """When wait_for_state completes before timeout, we expect our
        deferred to fire successfully.
        """
        self.sg.group_id = 'abc'
        self.sg.get_scaling_group_state = self.get_scaling_group_state_happy
        self.threshold = 25

        d = self.sg.wait_for_state(None, HasActive(2), clock=self.clock)
        for _ in range(24):
            self.clock.advance(10)
            self.assertNoResult(d)
        self.clock.advance(10)
        self.successResultOf(d)

    def test_poll_until_timeout(self):
        """When wait_for_state exceeds a maximum time threshold, we expect
        it to raise an exception.
        """
        self.sg.group_id = 'abc'
        self.sg.get_scaling_group_state = self.get_scaling_group_state_timeout

        d = self.sg.wait_for_state(None, HasActive(2), clock=self.clock)
        for _ in range(59):
            self.clock.advance(10)
            self.assertNoResult(d)
        self.clock.advance(10)
        self.failureResultOf(d, TimedOutError)


class MatcherTestCase(SynchronousTestCase):
    """
    Tests for the CLB matchers.
    """
    def test_exclude_servers_success(self):
        """
        :class:`ExcludesServers` succeeds when the active list does not contain
        any servers with the given server IDS
        """
        matcher = ExcludesServers(['id1', 'id2'])
        mismatch = matcher.match(
            {'active': [{'id': "id{0}".format(i)} for i in (3, 4)]}
        )
        self.assertEqual(mismatch, None)

    def test_excludes_servers_failure(self):
        """
        :class:`ExcludesServers` fails when the active list contain any or all
        of servers with the given IDs.
        """
        matcher = ExcludesServers(['id1', 'id2'])
        self.assertNotEqual(
            matcher.match(
                {'active': [{'id': "id{0}".format(i)} for i in (1, 2)]}),
            "Complete match succeeds when none should be present.",
            None
        )
        self.assertNotEqual(
            matcher.match({'active': [{'id': "id1"}]}),
            "Partial match succeeds when none should be present.",
            None
        )

    def test_has_active(self):
        """
        :class:`HasActive` only succeeds when the number of active servers
        matches the length given.
        """
        matcher = HasActive(2)
        self.assertNotEqual(matcher.match({'active': [{'id': "id1"}]}), None)
        self.assertNotEqual(matcher.match({'active': []}), None)
        self.assertEqual(
            matcher.match(
                {'active': [{'id': "id{0}".format(i)} for i in (1, 2)]}),
            None)


class GetServicenetIPs(SynchronousTestCase):
    """
    Tests for :func:`ScalingGroup.get_servicenet_ips`.
    """
    def setUp(self):
        """Create our simulated clock and scaling group."""
        self.clock = Clock()
        self.pool = object()
        self.treq = object()
        self.queried_server_ids = []

        class FakeRCS(object):
            endpoints = {'nova': 'novaurl'}
            token = "token"

        @attributes(['id', 'pool', 'treq'])
        class FakeNova(object):
            def get_addresses(nova_self, rcs):
                self.assertIs(nova_self.pool, self.pool)
                self.assertIs(nova_self.treq, self.treq)
                self.queried_server_ids.append(nova_self.id)
                return defer.succeed({
                    'addresses': {
                        'private': [
                            {'addr': '10.0.0.{0}'.format(
                                len(self.queried_server_ids)),
                             'version': 4}
                        ]
                    }
                })

        self.rcs = FakeRCS()
        self.sg = ScalingGroup(group_config={}, pool=self.pool,
                               reactor=self.clock, treq=self.treq,
                               server_client=FakeNova)

    def test_queries_for_provided_server_ids(self):
        """
        If server IDs are provided, IPs are queried for those server IDs.
        And if the same server ID is given multiple times, only one query is
        made for any given server ID.
        """
        server_ids = ['1', '2', '2', '2', '3']
        d = self.sg.get_servicenet_ips(self.rcs, server_ids)
        result = self.successResultOf(d)
        self.assertEqual(['10.0.0.1', '10.0.0.2', '10.0.0.3'],
                         sorted(result.values()))
        self.assertEqual(['1', '2', '3'], sorted(result.keys()))
        self.assertEqual(['1', '2', '3'], sorted(self.queried_server_ids))

    def test_gets_active_server_ids_if_server_ids_not_provided(self):
        """
        If server IDs are not provided, IPs are queried for the active servers
        on the group server IDs.
        """
        def get_scaling_group_state(_, success_codes):
            self.assertEqual(success_codes, [200])
            return defer.succeed((
                200, {'group': {'active': [{'id': '11'}, {'id': '12'}]}}
            ))

        self.sg.get_scaling_group_state = get_scaling_group_state
        d = self.sg.get_servicenet_ips(self.rcs)
        self.assertEqual({'11': '10.0.0.1', '12': '10.0.0.2'},
                         self.successResultOf(d))
        self.assertEqual(['11', '12'], self.queried_server_ids)
