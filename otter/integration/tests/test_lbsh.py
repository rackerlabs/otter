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

from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue

from twisted.trial import unittest

from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer,
    ContainsAllIPs,
    ExcludesAllIPs,
    HasLength
)
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    region,
    skip_me
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

    @inlineCallbacks
    def create_another_clb(self):
        """
        Create another CLB and wait for it to become active.  It will not
        be added to the helper.  This is used, for example, to create a CLB
        that is not associated with an autoscaling group.
        """
        # Create another loadbalancer not to be used in autoscale
        # The CLB will not be added to the helper, since when the helper
        # creates a group, it automatically adds the clb
        clb_other = CloudLoadBalancer(pool=self.helper.pool,
                                      treq=self.helper.treq)
        yield clb_other.start(self.rcs, self)
        yield clb_other.wait_for_state(
            self.rcs, "ACTIVE", timeout_default)
        returnValue(clb_other)

    @inlineCallbacks
    def confirm_clb_nodecounts(self, clbs):
        """
        Confirm that the provided CLBs have no nodes.

        :param list clbs: a `list` of `tuple` of (:obj:`CloudLoadBalancer`,
            number of expected nodes)

        :return: `list` of nodes in the same order as the CLBs given
        """
        nodes = yield gatherResults([
            clb.wait_for_nodes(
                self.rcs, HasLength(numnodes), timeout=timeout_default)
            for clb, numnodes in clbs
        ])
        returnValue(nodes)

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
        yield self.confirm_clb_nodecounts([(clb, 0)])

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        clbs_nodes = yield self.confirm_clb_nodecounts([(clb, 1)])
        the_node = clbs_nodes[0][0]

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

    @inlineCallbacks
    def test_move_node_to_oob_lb(self):
        """
        1 group, LB1 in config, LB2 not in any autoscale configs:

        Server node moved from LB1 to LB2
        Assert: Server put back on LB1
        Assert: Server removed from LB2
        """
        clb_as = self.helper.clbs[0]
        clb_other = yield self.create_another_clb()

        yield self.confirm_clb_nodecounts([(clb_as, 0), (clb_other, 0)])

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        nodes = yield self.confirm_clb_nodecounts([(clb_as, 1),
                                                   (clb_other, 0)])
        nodes_as = nodes[0]

        the_node = nodes_as[0]
        node_info = {
            "address": the_node["address"],
            "port": the_node["port"],
            "condition": the_node["condition"],
            "weight": 2
        }

        yield clb_as.delete_nodes(self.rcs, [the_node['id']])
        yield clb_other.add_nodes(self.rcs, [node_info])
        yield self.confirm_clb_nodecounts([(clb_as, 0), (clb_other, 1)])

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

    @inlineCallbacks
    def test_oob_copy_node_to_oob_lb(self):
        """
        This is a slight variation of :func:`test_move_node_to_oob_lb`, with
        the node copied to the second load balancer instead of moved.

        Confirm that when convergence is triggered, nodes copied to
        non-autoscale loadbalancers are removed.

        1 group, LB1 in config, LB2 not in any autoscale configs:
            - Server node added to LB2 (now on both)
            - Trigger convergence
            - Assert: Server still on LB1
            - Assert: Server removed from LB2
        """
        clb_as = self.helper.clbs[0]
        clb_other = yield self.create_another_clb()
        yield self.confirm_clb_nodecounts([(clb_as, 0), (clb_other, 0)])

        group, _ = self.helper.create_group(min_entities=1)
        yield self.helper.start_group_and_wait(group, self.rcs)

        # One node should have been added to clb_as, none to clb_other
        nodes = yield self.confirm_clb_nodecounts([(clb_as, 1),
                                                   (clb_other, 0)])
        nodes_as = nodes[0]

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

        nodes = yield clb.list_nodes(self.rcs)
        self.assertEqual(len(nodes['nodes']), 0,
                         "There should be no nodes on the CLB yet.")

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

    @inlineCallbacks
    def _disown_change_and_converge(self, remove_from_clb=True):
        """
        Test helper for
        :func:`test_changing_disowned_server_is_not_converged_1` and
        :func:`test_changing_disowned_server_is_not_converged_2`.

        Create an AS group with 2 servers, disowns 1 of them, perterbs the
        CLBs they are on, and then triggers convergence.
        """
        clb_as = self.helper.clbs[0]
        clb_other = yield self.create_another_clb()
        yield self.confirm_clb_nodecounts([(clb_as, 0), (clb_other, 0)])

        group, _ = self.helper.create_group()
        yield self.helper.start_group_and_wait(group, self.rcs, desired=2)
        ips = yield group.get_servicenet_ips(self.rcs)
        disowned_server = ips.keys()[0]
        remaining_server = ips.keys()[1]

        yield group.disown(self.rcs, disowned_server)

        # copy/move the untouched server to the other CLB
        clb_manipulation = [
            clb_other.add_nodes(
                self.rcs,
                [{'address': ip, 'port': 80, 'condition': 'ENABLED',
                  'type': 'PRIMARY'} for ip in ips.values()])
        ]
        if remove_from_clb:
            nodes = yield clb_as.list_nodes(self.rcs)
            clb_manipulation.append(
                clb_as.delete_nodes(
                    self.rcs, [n['id'] for n in nodes['nodes']]))
        yield gatherResults(clb_manipulation)

        # trigger group
        yield group.trigger_convergence(self.rcs)

        returnValue((group, clb_as, clb_other, ips[disowned_server],
                     ips[remaining_server]))

    @skip_me("Otter bug 1698")
    @inlineCallbacks
    def test_changing_disowned_server_is_not_converged_1(
            self, remove_from_clb=True):
        """
        Moving a disowned autoscale server to a different CLB and converging
        will not move the disowned server back on its intended CLB.

        1. Create an AS group with 2 servers.
        2. Disown 1 server.
        3. Move both servers to a different CLB.
        4. Converge group.
        6. Assert that the group's server is back on its CLB, and that the
           disowned server's remains on the wrong CLB.
        """
        group, clb_as, clb_other, gone_ip, stay_ip = (
            yield self._disown_change_and_converge())

        yield gatherResults([
            clb_as.wait_for_nodes(
                self.rcs,
                MatchesAll(
                    ExcludesAllIPs([gone_ip]),
                    ContainsAllIPs([stay_ip]),
                    HasLength(1)
                ),
                timeout=timeout_default
            ),
            clb_other.wait_for_nodes(
                self.rcs,
                MatchesAll(
                    ExcludesAllIPs([stay_ip]),
                    ContainsAllIPs([gone_ip]),
                    HasLength(1)
                ),
                timeout=timeout_default
            ),
            group.wait_for_state(
                self.rcs,
                MatchesAll(
                    ContainsDict({
                        'pendingCapacity': Equals(0),
                        'desiredCapacity': Equals(1),
                        'status': Equals('ACTIVE'),
                        'active': HasLength(1)
                    })
                ),
                timeout=timeout_default
            )
        ])

    @skip_me("Otter bug 1698")
    @inlineCallbacks
    def test_changing_disowned_server_is_not_converged_2(self):
        """
        Copying a disowned autoscale server to a different CLB and converging
        will not move the disowned server back on its intended CLB.

        1. Create an AS group with 2 servers.
        2. Disown 1 server.
        3. Place both servers on a different CLB in addition to the original
           CLB.
        4. Converge group.
        6. Assert that the group's server is back on its CLB only, and that the
           disowned server's remains on both CLBs.

        This is slightly different than
        :func:`test_changing_disowned_server_is_not_converged_1` in that it
        does not remove the servers from their original CLB.  This tests
        that autoscale will not remove disowned servers from the original
        autoscale CLB.
        """
        group, clb_as, clb_other, gone_ip, stay_ip = (
            yield self._disown_change_and_converge(False))

        yield gatherResults([
            clb_as.wait_for_nodes(
                self.rcs,
                MatchesAll(
                    ContainsAllIPs([gone_ip, stay_ip]),
                    HasLength(2)
                ),
                timeout=timeout_default
            ),
            clb_other.wait_for_nodes(
                self.rcs,
                MatchesAll(
                    ExcludesAllIPs([stay_ip]),
                    ContainsAllIPs([gone_ip]),
                    HasLength(1)
                ),
                timeout=timeout_default
            ),
            group.wait_for_state(
                self.rcs,
                MatchesAll(
                    ContainsDict({
                        'pendingCapacity': Equals(0),
                        'desiredCapacity': Equals(1),
                        'status': Equals('ACTIVE'),
                        'active': HasLength(1)
                    })
                ),
                timeout=timeout_default
            )
        ])
