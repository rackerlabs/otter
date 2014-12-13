"""Tests for convergence planning."""

from pyrsistent import pmap, pbag, pset, s

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.model import (
    DesiredGroupState,
    LBConfig,
    LBNode,
    NodeCondition,
    NodeType,
    NovaServer,
    ServerState)
from otter.convergence.planning import (
    _converge_lb_state,
    _remove_from_lb_with_draining,
    converge,
    optimize_steps)
from otter.convergence.steps import (
    AddNodesToLoadBalancer,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeLoadBalancerNode,
    CreateServer,
    DeleteServer,
    RemoveFromLoadBalancer,
    SetMetadataItemOnServer)


class RemoveFromLBWithDrainingTests(SynchronousTestCase):
    """
    Tests for :func:`_remove_from_lb_with_draining`
    """
    def test_zero_timeout_remove_from_lb(self):
        """
        If the timeout is zero, all nodes are just removed
        """
        result = _remove_from_lb_with_draining(
            0,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80))],
            0)

        self.assertEqual(result, [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_disabled_state_is_removed(self):
        """
        Nodes in disabled state are just removed from the load balancer even
        if the timeout is positive
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DISABLED))],
            0)

        self.assertEqual(result, [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_enabled_state_is_drained(self):
        """
        Nodes in enabled state are put into draining.
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80))],
            0)

        self.assertEqual(
            result,
            [ChangeLoadBalancerNode(lb_id=5, node_id=123, weight=1,
                                    condition=NodeCondition.DRAINING,
                                    type=NodeType.PRIMARY)])

    def test_draining_state_is_ignored_if_connections_and_not_yet_timeout(self):
        """
        Nodes in draining state will be ignored if they still have connections
        and the timeout is not yet expired
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                    drained_at=0.0, connections=1)],
            5)

        self.assertEqual(result, [])

    def test_draining_state_removed_if_no_connections_and_not_yet_timeout(self):
        """
        Nodes in draining state will be removed if they have no more
        connections, even if the timeout is not yet expired
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                    drained_at=0.0, connections=0)],
            5)

        self.assertEqual(result, [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_draining_state_remains_if_connections_None_and_not_yet_timeout(self):
        """
        Nodes in draining state will be ignored if timeout has not yet expired
        and the number of active connections are not provided
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                    drained_at=0.0)],
            5)

        self.assertEqual(result, [])

    def test_draining_state_removed_if_connections_None_and_timeout_expired(self):
        """
        Nodes in draining state will be removed when the timeout expires if
        the number of active connections are not provided
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                    drained_at=0.0)],
            15)

        self.assertEqual(result, [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_draining_state_removed_if_connections_and_timeout_expired(self):
        """
        Nodes in draining state will be removed when the timeout expires even
        if they still have active connections
        """
        result = _remove_from_lb_with_draining(
            10,
            [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                    config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                    drained_at=0.0, connections=10)],
            15)

        self.assertEqual(result, [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_all_changes_together(self):
        """
        Given all possible combination of load balancer states and timeouts,
        ensure function produces the right set of step for all of them.
        """
        current = [
            # enabled, should be drained
            LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                   config=LBConfig(port=80)),
            # disabled, should be removed
            LBNode(lb_id=2, node_id=2, address='1.1.1.1',
                   config=LBConfig(port=80, condition=NodeCondition.DISABLED)),
            # draining, still connections, should be ignored
            LBNode(lb_id=3, node_id=3, address='1.1.1.1',
                   config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                   connections=3, drained_at=5.0),
            # draining, no connections, should be removed
            LBNode(lb_id=4, node_id=4, address='1.1.1.1',
                   config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                   connections=0, drained_at=5.0),
            # draining, timeout exired, should be removed
            LBNode(lb_id=5, node_id=5, address='1.1.1.1',
                   config=LBConfig(port=80, condition=NodeCondition.DRAINING),
                   connections=10, drained_at=0.0)]

        result = _remove_from_lb_with_draining(10, current, 10)
        self.assertEqual(set(result), set([
            ChangeLoadBalancerNode(lb_id=1, node_id=1, weight=1,
                                   condition=NodeCondition.DRAINING,
                                   type=NodeType.PRIMARY),
            RemoveFromLoadBalancer(lb_id=2, node_id=2),
            RemoveFromLoadBalancer(lb_id=4, node_id=4),
            RemoveFromLoadBalancer(lb_id=5, node_id=5),
        ]))


class ConvergeLBStateTests(SynchronousTestCase):
    """
    Tests for :func:`_converge_lb_state`
    """
    def test_add_to_lb(self):
        """
        If a desired LB config is not in the set of current configs,
        `converge_lb_state` returns a :class:`AddToLoadBalancer` object
        """
        result = _converge_lb_state(desired_lb_state={5: [LBConfig(port=80)]},
                                    current_lb_nodes=[],
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80))))])

    def test_change_lb_node(self):
        """
        If a desired LB mapping is in the set of current configs,
        but the configuration is wrong, `converge_lb_state` returns a
        :class:`ChangeLoadBalancerNode` object
        """
        desired = {5: [LBConfig(port=80)]}
        current = [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                          config=LBConfig(port=80, weight=5))]

        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_nodes=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [ChangeLoadBalancerNode(lb_id=5, node_id=123, weight=1,
                                    condition=NodeCondition.ENABLED,
                                    type=NodeType.PRIMARY)])

    def test_remove_lb_node(self):
        """
        If a current lb config is not in the desired set of lb configs,
        `converge_lb_state` returns a :class:`RemoveFromLoadBalancer` object
        """
        current = [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                          config=LBConfig(port=80, weight=5))]

        result = _converge_lb_state(desired_lb_state={},
                                    current_lb_nodes=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [RemoveFromLoadBalancer(lb_id=5, node_id=123)])

    def test_do_nothing(self):
        """
        If the desired lb state matches the current lb state,
        `converge_lb_state` returns nothing
        """
        desired = {5: [LBConfig(port=80)]}
        current = [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                          config=LBConfig(port=80))]

        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_nodes=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(list(result), [])

    def test_all_changes(self):
        """
        Remove, change, and add a node to a load balancer all together
        """
        desired = {5: [LBConfig(port=80)],
                   6: [LBConfig(port=80, weight=2)]}
        current = [LBNode(lb_id=5, node_id=123, address='1.1.1.1',
                          config=LBConfig(port=8080)),
                   LBNode(lb_id=6, node_id=234, address='1.1.1.1',
                          config=LBConfig(port=80))]

        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_nodes=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(set(result), set([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            ChangeLoadBalancerNode(lb_id=6, node_id=234, weight=2,
                                   condition=NodeCondition.ENABLED,
                                   type=NodeType.PRIMARY),
            RemoveFromLoadBalancer(lb_id=5, node_id=123)
        ]))

    def test_same_lb_multiple_ports(self):
        """
        It's possible to have the same load balancer using multiple ports on
        the host.

        (use case: running multiple single-threaded server processes on a
        machine)
        """
        desired = {5: [LBConfig(port=8080), LBConfig(port=8081)]}
        current = []
        result = _converge_lb_state(desired, current, '1.1.1.1')
        self.assertEqual(
            set(result),
            set([
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('1.1.1.1', LBConfig(port=8080)))),
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('1.1.1.1', LBConfig(port=8081))))
                ]))


def server(id, state, created=0, **kwargs):
    """Convenience for creating a :obj:`NovaServer`."""
    return NovaServer(id=id, state=state, created=created, **kwargs)


class DrainAndDeleteServerTests(SynchronousTestCase):
    """
    Tests for :func:`converge` having to do with draining and deleting servers.
    """
    def test_active_server_without_load_balancers_can_be_deleted(self):
        """
        If an active server to be scaled down is not attached to any load
        balancers, it can be deleted. It is not first put into draining state.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                set([server('abc', state=ServerState.ACTIVE)]),
                set(),
                0),
            pbag([DeleteServer(server_id='abc')]))

    def test_active_server_can_be_deleted_if_all_lbs_can_be_removed(self):
        """
        If an active server to be scaled down can be removed from all the load
        balancers, the server can be deleted.  It is not first put into
        draining state.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                set([server('abc', state=ServerState.ACTIVE,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80))]),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=1, node_id=1)
            ]))

    def test_draining_server_can_be_deleted_if_all_lbs_can_be_removed(self):
        """
        If draining server can be removed from all the load balancers, the
        server can be deleted.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                set([server('abc', state=ServerState.DRAINING,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80,
                            condition=NodeCondition.DRAINING))]),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=1, node_id=1)
            ]))

    def test_draining_server_ignored_if_waiting_for_timeout(self):
        """
        If the server already in draining state is waiting for the draining
        timeout on some load balancers, nothing is done to it.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                set([server('abc', state=ServerState.DRAINING,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80,
                            condition=NodeCondition.DRAINING),
                            drained_at=1.0, connections=1)]),
                2),
            pbag([]))

    def test_active_server_is_drained_if_not_all_lbs_can_be_removed(self):
        """
        If an active server to be deleted cannot be removed from all the load
        balancers, it is set to draining state and all the nodes are set to
        draining condition.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                set([server('abc', state=ServerState.ACTIVE,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80))]),
                0),
            pbag([
                ChangeLoadBalancerNode(lb_id=1, node_id=1, weight=1,
                                       condition=NodeCondition.DRAINING,
                                       type=NodeType.PRIMARY),
                SetMetadataItemOnServer(server_id='abc',
                                        key='rax:auto_scaling_draining',
                                        value='draining')
            ]))

    def test_active_server_is_drained_even_if_all_already_in_draining(self):
        """
        If an active server already has all of its load balancers in draining,
        but it cannot be removed from all of them yet, it is set to draining
        state even though no load balancer actions need to be performed.

        This can happen for instance if the server was supposed to be deleted
        in a previous convergence run, and the load balancers were set to
        draining but setting the server metadata failed.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                set([server('abc', state=ServerState.ACTIVE,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80,
                                            condition=NodeCondition.DRAINING),
                            connections=1, drained_at=0.0)]),
                1),
            pbag([
                SetMetadataItemOnServer(server_id='abc',
                                        key='rax:auto_scaling_draining',
                                        value='draining')
            ]))

    def test_draining_server_has_all_enabled_lb_set_to_draining(self):
        """
        If a draining server is enabled on any load balancers, it is set to
        draining on those load balancers and it is not deleted.  The metadata
        is not re-set to draining.

        This can happen for instance if the server was supposed to be deleted
        in a previous convergence run, and the server metadata was set but
        the load balancers update failed.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                set([server('abc', state=ServerState.DRAINING,
                            servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                            config=LBConfig(port=80))]),
                1),
            pbag([
                ChangeLoadBalancerNode(lb_id=1, node_id=1, weight=1,
                                       condition=NodeCondition.DRAINING,
                                       type=NodeType.PRIMARY)
            ]))


class ConvergeTests(SynchronousTestCase):
    """Tests for :func:`converge`."""

    def test_converge_give_me_a_server(self):
        """
        A server is added if there are not enough servers to meet
        the desired capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                set(),
                set(),
                0),
            pbag([CreateServer(launch_config=pmap())]))

    def test_converge_give_me_multiple_servers(self):
        """
        Multiple servers are added at a time if there are not enough servers to
        meet the desired capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                set(),
                set(),
                0),
            pbag([
                CreateServer(launch_config=pmap()),
                CreateServer(launch_config=pmap())]))

    def test_count_building_as_meeting_capacity(self):
        """
        No servers are created if there are building servers that sum with
        active servers to meet capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                set([server('abc', ServerState.BUILD)]),
                set(),
                0),
            pbag([]))

    def test_delete_nodes_in_error_state(self):
        """
        If a server we created enters error state, it will be deleted if
        necessary, and replaced.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                set([server('abc', ServerState.ERROR)]),
                set(),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                CreateServer(launch_config=pmap()),
            ]))

    def test_delete_error_state_servers_with_lb_nodes(self):
        """
        If a server we created enters error state and it is attached to one
        or more load balancers, it will be removed from its load balancers
        as well as get deleted.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                set([server('abc', ServerState.ERROR, servicenet_address='1.1.1.1')]),
                set([LBNode(lb_id=5, address='1.1.1.1', node_id=3,
                            config=LBConfig(port=80)),
                     LBNode(lb_id=5, address='1.1.1.1', node_id=5,
                            config=LBConfig(port=8080))]),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=5, node_id=3),
                RemoveFromLoadBalancer(lb_id=5, node_id=5),
                CreateServer(launch_config=pmap()),
            ]))

    def test_scale_down(self):
        """If we have more servers than desired, we delete the oldest."""
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                set([server('abc', ServerState.ACTIVE, created=0),
                     server('def', ServerState.ACTIVE, created=1)]),
                set(),
                0),
            pbag([DeleteServer(server_id='abc')]))

    def test_scale_down_with_lb_nodes(self):
        """
        When scaling down, if there are any servers to be deleted that are
        attached to existing load balancers, they will also be also removed
        from said load balancers
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                set([server('abc', ServerState.ACTIVE,
                            servicenet_address='1.1.1.1', created=0)]),
                set([LBNode(lb_id=5, address='1.1.1.1', node_id=3,
                            config=LBConfig(port=80))]),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=5, node_id=3)
            ]))

    def test_scale_down_building_first(self):
        """
        When scaling down, first we delete building servers, in preference
        to older server.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                set([server('abc', ServerState.ACTIVE, created=0),
                     server('def', ServerState.BUILD, created=1),
                     server('ghi', ServerState.ACTIVE, created=2)]),
                set(),
                0),
            pbag([DeleteServer(server_id='def')]))

    def test_timeout_building(self):
        """
        Servers that have been building for too long will be deleted and
        replaced.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                set([server('slowpoke', ServerState.BUILD, created=0),
                     server('ok', ServerState.ACTIVE, created=0)]),
                set(),
                3600),
            pbag([
                DeleteServer(server_id='slowpoke'),
                CreateServer(launch_config=pmap())]))

    def test_timeout_replace_only_when_necessary(self):
        """
        If a server is timing out *and* we're over capacity, it will be
        deleted without replacement.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                set([server('slowpoke', ServerState.BUILD, created=0),
                     server('old-ok', ServerState.ACTIVE, created=0),
                     server('new-ok', ServerState.ACTIVE, created=3600)]),
                set(),
                3600),
            pbag([DeleteServer(server_id='slowpoke')]))

    def test_converge_active_servers_ignores_servers_to_be_deleted(self):
        """
        Only servers in active that are not being deleted will have their
        load balancers converged.
        """
        desired_lbs = {5: [LBConfig(port=80)]}
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1, desired_lbs=desired_lbs),
                set([server('abc', ServerState.ACTIVE,
                            servicenet_address='1.1.1.1', created=0),
                     server('bcd', ServerState.ACTIVE,
                            servicenet_address='2.2.2.2', created=1)]),
                set(),
                0),
            pbag([
                DeleteServer(server_id='abc'),
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('2.2.2.2', LBConfig(port=80))))
            ]))


class OptimizerTests(SynchronousTestCase):
    """Tests for :func:`optimize_steps`."""

    def test_optimize_lb_adds(self):
        """
        Multiple :class:`AddNodesToLoadBalancer` steps for the same LB
        are merged into one.
        """
        steps = pbag([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.2.3.4', LBConfig(port=80))))])
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(
                        ('1.1.1.1', LBConfig(port=80)),
                        ('1.2.3.4', LBConfig(port=80)))
                )]))

    def test_optimize_maintain_unique_ports(self):
        """
        Multiple ports can be specified for the same address and LB ID.
        """
        steps = pbag([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=8080))))])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('1.1.1.1', LBConfig(port=80)),
                                      ('1.1.1.1', LBConfig(port=8080))))]))

    def test_multiple_load_balancers(self):
        """Aggregation is done on a per-load-balancer basis."""
        steps = pbag([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.2', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=6,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=6,
                address_configs=s(('1.1.1.2', LBConfig(port=80)))),
        ])
        self.assertEqual(
            optimize_steps(steps),
            pbag([
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('1.1.1.1', LBConfig(port=80)),
                                      ('1.1.1.2', LBConfig(port=80)))),
                AddNodesToLoadBalancer(
                    lb_id=6,
                    address_configs=s(('1.1.1.1', LBConfig(port=80)),
                                      ('1.1.1.2', LBConfig(port=80)))),
            ]))

    def test_optimize_leaves_other_steps(self):
        """
        Unoptimizable steps pass the optimizer unchanged.
        """
        steps = pbag([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            CreateServer(launch_config=pmap({})),
            BulkRemoveFromRCv3(lb_node_pairs=pset([("lb-1", "node-a")])),
            BulkAddToRCv3(lb_node_pairs=pset([("lb-2", "node-b")]))
            # Note that the add & remove pair should not be the same;
            # the optimizer might reasonably optimize opposite
            # operations away in the future.
        ])
        self.assertEqual(
            optimize_steps(steps),
            steps)

    def test_mixed_optimization(self):
        """
        Mixes of optimizable and unoptimizable steps still get optimized
        correctly.
        """
        steps = pbag([
            # CLB adds
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.2', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=6,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            AddNodesToLoadBalancer(
                lb_id=6,
                address_configs=s(('1.1.1.2', LBConfig(port=80)))),

            # Unoptimizable steps
            CreateServer(launch_config=pmap({})),
        ])

        self.assertEqual(
            optimize_steps(steps),
            pbag([
                # Optimized CLB adds
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('1.1.1.1', LBConfig(port=80)),
                                      ('1.1.1.2', LBConfig(port=80)))),
                AddNodesToLoadBalancer(
                    lb_id=6,
                    address_configs=s(('1.1.1.1', LBConfig(port=80)),
                                      ('1.1.1.2', LBConfig(port=80)))),

                # Unoptimizable steps
                CreateServer(launch_config=pmap({}))
            ]))
