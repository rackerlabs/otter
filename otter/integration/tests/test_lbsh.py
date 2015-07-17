"""
Tests covering the Load Balancer self healing behaviors
"""

from __future__ import print_function

from testtools.matchers import (
    ContainsDict,
    Equals,
    MatchesAll,
    MatchesRegex,
    MatchesSetwise
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
    tag
)

timeout_default = 600


class TestLoadBalancerSelfHealing(unittest.TestCase):
    """
    This class contains test cases to test the load balancer healing
    function of the Otter Converger.
    """
    timeout = 1800

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

    @tag("LBSH-001")
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

        yield clb.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        nodes = yield clb.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)

        the_node = nodes[0]

        yield clb.delete_nodes(self.rcs, [the_node['id']])

        yield clb.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)
        yield group.trigger_convergence(self.rcs)

        yield clb.wait_for_nodes(
            self.rcs,
            MatchesAll(
                HasLength(1),
                ContainsAllIPs([the_node["address"]])
            ),
            timeout=timeout_default
        )

    @tag("LBSH-002")
    @inlineCallbacks
    def test_move_node_to_oob_lb(self):
        """
        1 group, LB1 in config, LB2 not in any autoscale configs:

        Server node moved from LB1 to LB2
        Assert: Server put back on LB1
        Assert: Server removed from LB2
        """
        # Create another loadbalancer not to be used in autoscale
        # The CLB will not be added to the helper, since when the helper
        # creates a group, it automatically adds the clb
        clb_other = CloudLoadBalancer(pool=self.helper.pool)

        yield clb_other.start(self.rcs, self)
        yield clb_other.wait_for_state(
            self.rcs, "ACTIVE", timeout_default)

        clb_as = self.helper.clbs[0]

        yield clb_as.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        nodes_as = yield clb_as.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        the_node = nodes_as[0]
        node_info = {
            "address": the_node["address"],
            "port": the_node["port"],
            "condition": the_node["condition"],
            "weight": 2
        }

        yield clb_as.delete_nodes(self.rcs, [the_node['id']])
        yield clb_other.add_nodes(self.rcs, [node_info])

        yield clb_as.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)

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

    @tag("LBSH-003")
    @inlineCallbacks
    def test_oob_copy_node_to_oob_lb(self):
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

        # Confirm both LBs are empty to start
        yield clb_as.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        # One node should have been added to clb_as, none to clb_other
        nodes_as = yield clb_as.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
            self.rcs, HasLength(0), timeout=timeout_default)

        the_node = nodes_as[0]
        node_info = {
            "address": the_node["address"],
            "port": the_node["port"],
            "condition": the_node["condition"],
            "weight": the_node["weight"]
        }

        yield clb_other.add_nodes(self.rcs, [node_info])

        yield clb_as.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)
        yield clb_other.wait_for_nodes(
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

    @tag("LBSH-004")
    @inlineCallbacks
    def test_only_autoscale_nodes_are_modified(self):
        """
        Autoscale only self-heals the nodes that it added, without touching
        any other nodes.  Assuming 1 CLB:
        1. Create two non-autoscaled servers and add them to the CLB.
        2. Wait for all servers to be on the CLB
        3. Create a scaling group with said CLB and 1 server
        4. Wait for AS server to be active and on the CLB.
        4. Delete autoscaled server and 1 non-autoscaled server from the CLB
        5. Converge
        6. Assert that the autoscaled server is put back on the CLB, the
           non-autoscaled server is left off the CLB, and the untouched
           non-autoscaled server is left on the CLB.
        """
        clb = self.helper.clbs[0]

        yield clb.wait_for_nodes(self.rcs, HasLength(0),
                                 timeout=timeout_default)

        # create the other two non-autoscaled servers - just wait until they
        # have servicenet addresses - don't bother waiting for them to be
        # active, which will take too long
        other_servers = yield self.helper.create_servers(
            self.rcs, 2, wait_for=ContainsDict({
                "addresses": ContainsDict({
                    'private': MatchesSetwise(
                        ContainsDict({
                            "addr": MatchesRegex("(\d+\.){3}\d+")
                        })
                    )
                })
            }))
        # add non-autoscaled servers to the CLB
        clb_response = yield clb.add_nodes(
            self.rcs,
            [{'address': server['addresses']['private'][0]['addr'],
              'port': 8080,
              'condition': "ENABLED"} for server in other_servers])
        remove_non_as_node, untouch_non_as_node = clb_response['nodes']

        # set up the group and get the group's server's CLB node
        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        # Should be 3 nodes now that all servers are added
        nodes = yield clb.wait_for_nodes(
            self.rcs, HasLength(3), timeout=timeout_default)
        as_node = [node for node in nodes
                   if node not in (remove_non_as_node, untouch_non_as_node)][0]

        # delete 1 autoscale node and 1 non-autoscale node
        yield clb.delete_nodes(self.rcs,
                               [as_node['id'], remove_non_as_node['id']])
        # There should be 1 node left
        yield clb.wait_for_nodes(
            self.rcs, HasLength(1), timeout=timeout_default)

        yield group.trigger_convergence(self.rcs)

        yield clb.wait_for_nodes(
            self.rcs,
            MatchesSetwise(  # means there are only these two nodes and no more
                # the untouched node should remain exactly the same
                Equals(untouch_non_as_node),
                # the AS node should have the same paramters, but not the same
                # ID since it was re-added
                ContainsDict({
                    k: Equals(v) for k, v in as_node.items()
                    if k in ('address', 'port', 'weight' 'type', 'condition')
                })
            ),
            timeout=timeout_default
        )
