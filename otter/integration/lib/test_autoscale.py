"""Autoscale utility tests."""

from __future__ import print_function

from twisted.internet import defer
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.autoscale import ScalingGroup
from otter.integration.lib.autoscale import TimeoutError


class WaitForNServersTestCase(SynchronousTestCase):
    def setUp(self):
        """Create our simulated clock and scaling group.  We link the group
        to the clock, giving us explicit (and, for the purposes of our test,
        synchronous) control over the scaling group's concept of elapsed time.
        """

        self.clock = Clock()
        self.sg = ScalingGroup(group_config={}, pool=None, reactor=self.clock)
        # Replace method so we don't touch network resources.
        self.sg.get_scaling_group_state = self.get_scaling_group_state

    def get_scaling_group_state(self, rcs):
        """This method implements a synchronous simulation of what we'd expect
        to see over the wire on an HTTP API transaction.  This method replaces
        the actual ScalingGroup method on instances.  (See setUp for an example
        of how this method is used.)
        """

        return defer.succeed((200, {}))

    def test_poll_until_timeout(self):
        """When wait_for_N_servers exceeds a maximum time threshold, we expect
        it to raise an exception.
        """

        d = self.sg.wait_for_N_servers(None, 2, clock=self.clock)
#       d.callback(None)
        for _ in range(59):
            self.clock.advance(10)
            self.assertNoResult(d)
        self.clock.advance(10)
        self.failureResultOf(d, TimeoutError)
        
