"""
Tests covering `../groups/groupId/pause` and `../groups/groupId/resume`
endpoints
"""
from testtools.matchers import ContainsDict, Equals

import treq

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest

from otter.integration.lib.autoscale import ScalingPolicy
from otter.integration.lib.mimic import MimicNova
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    convergence_interval,
    get_identity,
    get_resource_mapping,
    get_utcstr_from_now,
    not_mimic,
    region,
    scheduler_interval,
    skip_if,
    sleep
)


timeout_default = 600


class PauseResumeTests(unittest.TestCase):
    """
    Tests for `../groups/groupId/pause` and `../groups/groupId/resume` endpoint
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

    @inlineCallbacks
    def test_pause_getstate(self):
        """
        A paused group's state will say paused:True
        """
        group, _ = self.helper.create_group()
        yield group.start(self.rcs, self)
        yield self.helper.assert_group_state(
            group, ContainsDict({"paused": Equals(False)}))
        yield group.pause(self.rcs)
        yield self.helper.assert_group_state(
            group, ContainsDict({"paused": Equals(True)}))

    @skip_if(not_mimic, "This requires mimic for long builds")
    @inlineCallbacks
    def test_pause_stops_convergence(self):
        """
        Pausing a group will stop any further convergence cycle. We do this by
        1. Setup mimic to build server for just before timeout
        2. Creating a group with 1 min entity
        3. Pause the group
        4. Wait for server to finish building in mimic
        5. Notice that group continues to think that server is building
        """
        mimic_nova = MimicNova(pool=self.helper.pool, test_case=self)
        server_build_time = convergence_interval + 5
        yield mimic_nova.sequenced_behaviors(
            self.rcs,
            criteria=[{"server_name": "pause-stops-convergence" + ".*"}],
            behaviors=[
                {"name": "build",
                 "parameters": {"duration": server_build_time}}
            ])
        group, _ = self.helper.create_group(min_entities=1)
        yield group.start(self.rcs, self)
        one_building = ContainsDict({"pendingCapacity": Equals(1),
                                     "activeCapacity": Equals(0),
                                     "desiredCapacity": Equals(1),
                                     "status": Equals("ACTIVE")})
        yield self.helper.assert_group_state(group, one_building)
        yield group.pause(self.rcs)
        # Wait for server to build and few more convergence cycles after that
        yield sleep(reactor,
                    server_build_time + convergence_interval * 2)
        # The group still thinks that server is building
        yield self.helper.assert_group_state(group, one_building)
        returnValue(group)

    @skip_if(not_mimic, "This requires mimic for server build time")
    @inlineCallbacks
    def test_resume(self):
        """
        Calling resume on a paused group changes {"paused": False} in group
        state and triggers convergence. The group can then execute policy,
        webhook or trigger convergence
        """
        group = yield self.test_pause_stops_convergence()
        yield group.resume(self.rcs)
        yield self.helper.assert_group_state(
            group, ContainsDict({"paused": Equals(False)}))
        yield group.wait_for_state(
            self.rcs,
            ContainsDict({"activeCapacity": Equals(1),
                          "pendingCapacity": Equals(0),
                          "desiredCapacity": Equals(1),
                          "status": Equals("ACTIVE")}))

        # can create and execute policy
        policy = ScalingPolicy(scale_by=1, scaling_group=group)
        yield policy.start(self.rcs, self)
        yield policy.execute(self.rcs)
        yield group.wait_for_state(
            self.rcs,
            ContainsDict({"activeCapacity": Equals(2),
                          "pendingCapacity": Equals(0),
                          "desiredCapacity": Equals(2),
                          "status": Equals("ACTIVE")}))

        # can create and execute webhooks
        webhook = yield policy.create_webhook(self.rcs)
        resp = yield treq.post(webhook.capurl, pool=self.helper.pool)
        self.assertEqual(resp.code, 202)
        yield treq.content(resp)
        yield sleep(reactor, 2)
        yield group.wait_for_state(
            self.rcs,
            ContainsDict({"activeCapacity": Equals(3),
                          "pendingCapacity": Equals(0),
                          "desiredCapacity": Equals(3),
                          "status": Equals("ACTIVE")}))

        # can trigger convergence
        yield group.trigger_convergence(self.rcs)

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
        returnValue((group, policy))

    @inlineCallbacks
    def test_pause_and_create_execute_webhook(self):
        """
        Webhook can be created on a paused group but it cannot be executed
        """
        group, policy = yield self.test_pause_and_create_policy()
        webhook = yield policy.create_webhook(self.rcs)
        # execute webhook and wait for sometime for execution to take place
        resp = yield treq.post(webhook.capurl, pool=self.helper.pool)
        self.assertEqual(resp.code, 202)
        yield treq.content(resp)
        yield sleep(reactor, 2)
        # The group has no impact
        yield self.helper.assert_group_state(
            group,
            ContainsDict({"pendingCapacity": Equals(0),
                          "desiredCapacity": Equals(0),
                          "activeCapacity": Equals(0)}))

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
        yield self.helper.assert_group_state(
            group,
            ContainsDict({
                "pendingCapacity": Equals(0),
                "activeCapacity": Equals(0),
                "desiredCapacity": Equals(0)}))
