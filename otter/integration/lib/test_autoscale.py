"""Autoscale utility tests."""

from __future__ import print_function

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.autoscale import ScalingGroup
from otter.integration.lib.autoscale import TimeoutError


class WaitForNServersTestCase(SynchronousTestCase):
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

    def get_scaling_group_state_happy(self, rcs):
        """This method implements a synchronous simulation of what we'd expect
        to see over the wire on an HTTP API transaction.  This method replaces
        the actual ScalingGroup method on instances.  (See setUp for an example
        of how this method is used.)

        This version emulates completion after a period of time.
        """

        if self.counter == self.threshold:
            return defer.succeed((200, self.group_state_w_2_servers))
        else:
            self.counter = self.counter + 1
            return defer.succeed((200, self.empty_group_state))

    def get_scaling_group_state_timeout(self, rcs):
        """This method implements a synchronous simulation of what we'd expect
        to see over the wire on an HTTP API transaction.  This method replaces
        the actual ScalingGroup method on instances.  (See setUp for an example
        of how this method is used.)

        This version never yields the desired number of servers.
        """

        return defer.succeed((200, self.empty_group_state))

    def test_poll_until_happy(self):
        """When wait_for_N_servers completes before timeout, we expect our
        deferred to fire successfully.
        """

        self.sg.get_scaling_group_state = self.get_scaling_group_state_happy
        self.threshold = 25

        d = self.sg.wait_for_N_servers(None, 2, clock=self.clock)
        for _ in range(24):
            self.clock.advance(10)
            self.assertNoResult(d)
        self.clock.advance(10)
        self.successResultOf(d)

    def test_poll_until_timeout(self):
        """When wait_for_N_servers exceeds a maximum time threshold, we expect
        it to raise an exception.
        """

        self.sg.get_scaling_group_state = self.get_scaling_group_state_timeout

        d = self.sg.wait_for_N_servers(None, 2, clock=self.clock)
        for _ in range(59):
            self.clock.advance(10)
            self.assertNoResult(d)
        self.clock.advance(10)
        self.failureResultOf(d, TimeoutError)
