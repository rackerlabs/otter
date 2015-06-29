"""
Tests covering the Load Balancer self healing behaviors
"""

from __future__ import print_function

from testtools.matchers import (
    MatchesAll
)

from twisted.internet.defer import gatherResults, inlineCallbacks

from twisted.trial import unittest

from otter.integration.lib.cloud_load_balancer import (
    ContainsAllIPs,
    HasLength
)
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    region,
    tag
)

timeout_default = 600


class TestLoadBalancerSelfHealing(unittest.TestCase):
    """
    This class contains test cases to test the load balancer healing
    functino of the Otter Converger.
    """

    def setUp(self):
        """
        Establish resources used for each test, such as the auth token
        and a load balancer.
        """

        self.helper = TestHelper(self, num_clbs=1)
        self.rcs = TestResources()
        self.identity = get_identity(pool=self.helper.pool)
        return self.identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region,
        ).addCallback(lambda _: gatherResults([
            clb.start(self.rcs, self)
            .addCallback(clb.wait_for_state, "ACTIVE", timeout_default)
            for clb in self.helper.clbs])
        )

    @tag("LBSH")
    @inlineCallbacks
    def test_oob_deleted_clb_node(self):
        """
        If an autoscaled server is removed from the CLB out of band its
        supposed to be on, Otter will put it back.

        1. Create a scaling group with 1 CLB and 1 server
        2. Wait for server to be active
        3. Delete server from the CLB
        4. Converge
        5. Assert that the server is put back on the CLB.
        """
        clb = self.helper.clbs[0]

        nodes = yield clb.list_nodes(self.rcs)
        self.assertEqual(len(nodes['nodes']), 0,
                         "There should be no nodes on the CLB yet.")

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        nodes = yield clb.list_nodes(self.rcs)
        self.assertEqual(
            len(nodes['nodes']), 1,
            "There should be 1 node on the CLB now that the group is active.")
        the_node = nodes["nodes"][0]

        yield clb.delete_nodes(self.rcs, [the_node['id']])

        nodes = yield clb.list_nodes(self.rcs)
        self.assertEqual(len(nodes['nodes']), 0,
                         "There should no nodes on the CLB after deletion.")

        yield group.trigger_convergence(self.rcs)

        yield clb.wait_for_nodes(
            self.rcs,
            MatchesAll(
                HasLength(1),
                ContainsAllIPs([the_node["address"]])
            ),
            timeout=timeout_default
        )
