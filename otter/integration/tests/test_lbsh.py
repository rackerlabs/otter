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
    CloudLoadBalancer,
    ContainsAllIPs,
    HasLength
)
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    region,
    skip_me,
    tag
)

timeout_default = 600


class TestLoadBalancerSelfHealing(unittest.TestCase):
    """
    This class contains test cases to test the load balancer healing
    function of the Otter Converger.
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

    @skip_me("temp")
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

        @tag("LBSH-003")
        @inlineCallbacks
        def test_lbsh_3(self):
            """
            This is a slight variation of lbsh-002, with the node being
            copied to the second load balancer instead of moved.

            Confirm that when convergence is triggered, nodes copied to
            non-autoscale loadbalancers are removed.

            1 group, LB1 in config, LB2 not in any autoscale configs:
                - Server node added to LB2 (now on both)
                - Trigger convergence
                - Assert: Server still on LB1
                - Assert: Server removed from LB2
            """

        # Create another loadbalancer not to be used in autoscale
        # The CLB will not be added to the helper, since when the helper
        # creates a group, it automatically adds the clb
        clb_other = CloudLoadBalancer(pool=self.helper.pool)

        yield clb_other.start(self.rcs, self)
        yield clb_other.wait_for_state(
            self.rcs, "ACTIVE", timeout_default)

        clb_as = self.helper.clbs[0]

        nodes_as = yield clb_as.list_nodes(self.rcs)

        # Confirm both LBs are empty to start
        clb_as.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)
        clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        # One node should have been added to clb_as, none to clb_other
        clb_as.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)
        clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        nodes_as = yield clb_as.list_nodes(self.rcs)

        the_node = nodes_as["nodes"][0]
        node_info = {
            "address": the_node["address"],
            "port": the_node["port"],
            "condition": the_node["condition"],
            "weight": the_node["weight"]
        }

        yield clb_other.add_nodes(self.rcs, [node_info])

        clb_as.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)
        clb_other.wait_for_nodes(
            self.rcs,
            MatchesAll(
                HasLength(1),
                ContainsAllIPs([the_node["address"]])
            ),
            timeout=timeout_default
        )

        yield group.trigger_convergence(self.rcs)

        yield clb_as.wait_for_nodes(
            self.rcs,
            MatchesAll(
                HasLength(1),
                ContainsAllIPs([the_node["address"]])
            ),
            timeout=timeout_default
        )

        yield clb_other.wait_for_nodes(
            self.rcs,
            HasLength(0),
            timeout=timeout_default
        )
