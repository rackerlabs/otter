"""
Tests covering `../groups/groupId/pause` and `../groups/groupId/resume`
endpoints
"""
from testtools.matchers import ContainsDict, Equals

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from otter.integration.lib.autoscale import ScalingPolicy
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    get_utcstr_from_now,
    region,
    scheduler_interval,
    sleep
)


timeout_default = 600


class PauseTests(unittest.TestCase):
    """
    Tests for `../groups/groupId/pause` endpoint
    """

    def setUp(self):
        self.helper = TestHelper(self)
        self.rcs = TestResources()
        self.identity = get_identity(self.helper.pool)
        return self.identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region
        )

    def test_pause_stops_convergence(self):
        """
        Pausing a group will stop any further convergence cycle. We do this by
        1. Setup mimic to keep building server
        2. Creating a group with 1 min entity
        3. Pause the group
        4. Finish building server in mimic
        5. Notice that group continues to think that server is building
        """

    @inlineCallbacks
    def test_pause_and_execute_policy(self):
        """
        Executing any policy of a paused group will result in 403
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        policy = ScalingPolicy(set_to=1, scaling_group=group)
        yield policy.start(self.rcs, self)
        yield group.pause(self.rcs)
        yield policy.execute(self.rcs, [403])

    @inlineCallbacks
    def test_pause_and_create_policy(self):
        """
        Policy can be created on a paused group
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        yield group.pause(self.rcs)
        policy = ScalingPolicy(set_to=1, scaling_group=group)
        yield policy.start(self.rcs, self)

    @inlineCallbacks
    def test_pause_and_converge(self):
        """
        Calling `../groups/groupId/converge` on a paused group will result
        in 403
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        yield group.pause(self.rcs)
        yield group.trigger_convergence(self.rcs, [403])

    @inlineCallbacks
    def test_pause_and_scheduled_policy(self):
        """
        A scheduled policy is not executed on a paused group
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        policy = ScalingPolicy(
            set_to=1, scaling_group=group,
            schedule={"at": get_utcstr_from_now(5)})
        yield policy.start(self.rcs, self)
        yield group.pause(self.rcs)
        yield sleep(reactor, 5 + scheduler_interval + 2)
        resp, state = yield group.get_scaling_group_state(self.rcs, [200])
        matcher = ContainsDict({
            "pendingCapacity": Equals(0),
            "activeCapacity": Equals(0),
            "desiredCapacity": Equals(0)})
        self.assertIsNone(matcher.match(state["group"]))

    @inlineCallbacks
    def test_delete_paused_group(self):
        """
        Deleting a paused group with force=false results in 403
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        yield group.pause(self.rcs)
        yield group.delete_scaling_group(self.rcs, "false", [403])

    @inlineCallbacks
    def test_force_delete_paused_group(self):
        """
        Deleting a paused froup with force=true succeeds
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        yield group.pause(self.rcs)
        yield group.delete_scaling_group(self.rcs, "true")
