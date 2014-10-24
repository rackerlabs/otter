"""Tests for convergence."""

import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import succeed

from otter.test.utils import StubTreq2, patch, iMock
from otter.auth import IAuthenticator
from otter.util.http import headers, APIError
from otter.convergence import (
    _remove_from_lb_with_draining, _converge_lb_state,
    get_all_server_details, get_scaling_group_servers,
    converge, Convergence, CreateServer, DeleteServer,
    RemoveFromLoadBalancer, ChangeLoadBalancerNode, AddNodesToLoadBalancer,
    SetMetadataItemOnServer,
    DesiredGroupState, NovaServer, Request, LBConfig, LBNode,
    ServerState, ServiceType, NodeCondition, NodeType, optimize_steps)

from pyrsistent import pmap, pbag, s


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        """
        Setup stub clock, treq implementation and mock authenticator
        """
        self.clock = Clock()
        self.auth = iMock(IAuthenticator)
        self.auth.authenticate_tenant.return_value = succeed(('token', 'catalog'))
        self.peu = patch(self, 'otter.convergence.public_endpoint_url',
                         return_value='url')
        self.req = ('GET', 'url/servers/detail?limit=10', dict(headers=headers('token')))
        self.servers = [{'id': i} for i in range(9)]

    def test_get_all_less_limit(self):
        """
        `get_all_server_details` will not fetch again if first get returns results
        with size < limit
        """
        treq = StubTreq2([(self.req, (200, json.dumps({'servers': self.servers})))])
        d = get_all_server_details('tid', self.auth, 'service', 'ord',
                                   limit=10, clock=self.clock, _treq=treq)
        self.assertEqual(self.successResultOf(d), self.servers)

    def test_get_all_above_limit(self):
        """
        `get_all_server_details` will fetch again until batch returned has size < limit
        """
        servers = [{'id': i} for i in range(19)]
        req2 = ('GET', 'url/servers/detail?limit=10&marker=9', dict(headers=headers('token')))
        treq = StubTreq2([(self.req, (200, json.dumps({'servers': servers[:10]}))),
                          (req2, (200, json.dumps({'servers': servers[10:]})))])
        d = get_all_server_details('tid', self.auth, 'service', 'ord',
                                   limit=10, clock=self.clock, _treq=treq)
        self.assertEqual(self.successResultOf(d), servers)

    def test_get_all_retries_exp(self):
        """
        `get_all_server_details` will fetch again in exponential backoff form
        if request fails
        """
        data = json.dumps({'servers': self.servers})
        treq = StubTreq2([(self.req, [(500, 'bad data'), (401, 'unauth'),
                                      (200, data)])])
        d = get_all_server_details('tid', self.auth, 'service', 'ord',
                                   limit=10, clock=self.clock, _treq=treq)
        self.assertNoResult(d)
        self.clock.advance(2)
        self.assertNoResult(d)
        self.clock.advance(4)
        self.assertEqual(self.successResultOf(d), self.servers)

    def test_get_all_retries_times_out(self):
        """
        `get_all_server_details` will keep trying to fetch info and give up
        eventually
        """
        treq = StubTreq2([(self.req, [(500, 'bad data') for i in range(6)])])
        d = get_all_server_details('tid', self.auth, 'service', 'ord',
                                   limit=10, clock=self.clock, _treq=treq)
        self.assertNoResult(d)
        self.clock.pump([2 ** i for i in range(1, 6)])
        self.failureResultOf(d, APIError)


class GetScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_scaling_group_servers`
    """

    def setUp(self):
        """
        Mock and setup :func:`get_all_server_details`
        """
        self.mock_gasd = patch(self, 'otter.convergence.get_all_server_details')
        self.servers = []
        self.clock = None

        def gasd(*args, **kwargs):
            if args == ('t', 'a', 's', 'r') and kwargs == {'clock': self.clock}:
                return succeed(self.servers)

        # Setup function to return value only on expected args to avoid asserting
        # its called every time
        self.mock_gasd.side_effect = gasd

    def test_filters_no_metadata(self):
        """
        Does not include servers which do not have metadata in it
        """
        self.servers = [{'id': i} for i in range(10)]
        d = get_scaling_group_servers('t', 'a', 's', 'r')
        self.assertEqual(self.successResultOf(d), {})

    def test_filters_no_as_metadata(self):
        """
        Does not include servers which have metadata but does not have AS info in it
        """
        self.servers = [{'id': i, 'metadata': {}} for i in range(10)]
        self.clock = Clock()
        d = get_scaling_group_servers('t', 'a', 's', 'r', clock=self.clock)
        self.assertEqual(self.successResultOf(d), {})

    def test_returns_as_servers(self):
        """
        Returns servers with AS metadata in it grouped by scaling group ID
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': 10}])
        self.servers = as_servers + [{'metadata': 'junk'}] * 3
        d = get_scaling_group_servers('t', 'a', 's', 'r')
        self.assertEqual(
            self.successResultOf(d),
            {'a': as_servers[:5] + [as_servers[-1]], 'b': as_servers[5:8]})

    def test_filters_on_user_criteria(self):
        """
        Considers user provided filter if provided
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)])
        self.servers = as_servers + [{'metadata': 'junk'}] * 3
        d = get_scaling_group_servers('t', 'a', 's', 'r',
                                      server_predicate=lambda s: s['id'] % 3 == 0)
        self.assertEqual(
            self.successResultOf(d),
            {'a': [as_servers[0], as_servers[3]], 'b': [as_servers[6]]})


class ObjectStorageTests(SynchronousTestCase):
    """
    Tests for objects that store data such as :class:`LBConfig`
    """

    def test_lbconfig_default_weight_condition_and_type(self):
        """
        :obj:`LBConfig` only requires a port.  The other attributes have
        default values.
        """
        lb = LBConfig(port=80)
        self.assertEqual(lb.weight, 1)
        self.assertEqual(lb.condition, NodeCondition.ENABLED)
        self.assertEqual(lb.type, NodeType.PRIMARY)


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
                                    current_lb_state=[],
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
                                    current_lb_state=current,
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
                                    current_lb_state=current,
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
                                    current_lb_state=current,
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
                                    current_lb_state=current,
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
                [server('abc', state=ServerState.ACTIVE)],
                [],
                0),
            Convergence(steps=pbag([DeleteServer(server_id='abc')])))

    def test_active_server_can_be_deleted_if_all_lbs_can_be_removed(self):
        """
        If an active server to be scaled down can be removed from all the load
        balancers, the server can be deleted.  It is not first put into
        draining state.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                [server('abc', state=ServerState.ACTIVE,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80))],
                0),
            Convergence(steps=pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=1, node_id=1)
            ])))

    def test_draining_server_can_be_deleted_if_all_lbs_can_be_removed(self):
        """
        If draining server can be removed from all the load balancers, the
        server can be deleted.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                [server('abc', state=ServerState.DRAINING,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80,
                        condition=NodeCondition.DRAINING))],
                0),
            Convergence(steps=pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=1, node_id=1)
            ])))

    def test_draining_server_ignored_if_waiting_for_timeout(self):
        """
        If the server already in draining state is waiting for the draining
        timeout on some load balancers, nothing is done to it.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0,
                                  draining_timeout=10.0),
                [server('abc', state=ServerState.DRAINING,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80,
                        condition=NodeCondition.DRAINING),
                        drained_at=1.0, connections=1)],
                2),
            Convergence(steps=pbag([])))

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
                [server('abc', state=ServerState.ACTIVE,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80))],
                0),
            Convergence(steps=pbag([
                ChangeLoadBalancerNode(lb_id=1, node_id=1, weight=1,
                                       condition=NodeCondition.DRAINING,
                                       type=NodeType.PRIMARY),
                SetMetadataItemOnServer(server_id='abc',
                                        key='rax:auto_scaling_draining',
                                        value='draining')
            ])))

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
                [server('abc', state=ServerState.ACTIVE,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80,
                                        condition=NodeCondition.DRAINING),
                        connections=1, drained_at=0.0)],
                1),
            Convergence(steps=pbag([
                SetMetadataItemOnServer(server_id='abc',
                                        key='rax:auto_scaling_draining',
                                        value='draining')
            ])))

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
                [server('abc', state=ServerState.DRAINING,
                        servicenet_address='1.1.1.1')],
                [LBNode(lb_id=1, node_id=1, address='1.1.1.1',
                        config=LBConfig(port=80))],
                1),
            Convergence(steps=pbag([
                ChangeLoadBalancerNode(lb_id=1, node_id=1, weight=1,
                                       condition=NodeCondition.DRAINING,
                                       type=NodeType.PRIMARY)
            ])))


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
                [],
                [],
                0),
            Convergence(
                steps=pbag([CreateServer(launch_config=pmap())])))

    def test_converge_give_me_multiple_servers(self):
        """
        Multiple servers are added at a time if there are not enough servers to
        meet the desired capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                [],
                [],
                0),
            Convergence(
                steps=pbag([
                    CreateServer(launch_config=pmap()),
                    CreateServer(launch_config=pmap())])))

    def test_count_building_as_meeting_capacity(self):
        """
        No servers are created if there are building servers that sum with
        active servers to meet capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ServerState.BUILD)],
                [],
                0),
            Convergence(steps=pbag([])))

    def test_delete_nodes_in_error_state(self):
        """
        If a server we created enters error state, it will be deleted if
        necessary, and replaced.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ServerState.ERROR)],
                [],
                0),
            Convergence(
                steps=pbag([
                    DeleteServer(server_id='abc'),
                    CreateServer(launch_config=pmap()),
                ])))

    def test_delete_error_state_servers_with_lb_nodes(self):
        """
        If a server we created enters error state and it is attached to one
        or more load balancers, it will be removed from its load balancers
        as well as get deleted.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ServerState.ERROR, servicenet_address='1.1.1.1')],
                [LBNode(lb_id=5, address='1.1.1.1', node_id=3,
                        config=LBConfig(port=80)),
                 LBNode(lb_id=5, address='1.1.1.1', node_id=5,
                        config=LBConfig(port=8080))],
                0),
            Convergence(
                steps=pbag([
                    DeleteServer(server_id='abc'),
                    RemoveFromLoadBalancer(lb_id=5, node_id=3),
                    RemoveFromLoadBalancer(lb_id=5, node_id=5),
                    CreateServer(launch_config=pmap()),
                ])))

    def test_scale_down(self):
        """If we have more servers than desired, we delete the oldest."""
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ServerState.ACTIVE, created=0),
                 server('def', ServerState.ACTIVE, created=1)],
                [],
                0),
            Convergence(steps=pbag([DeleteServer(server_id='abc')])))

    def test_scale_down_with_lb_nodes(self):
        """
        When scaling down, if there are any servers to be deleted that are
        attached to existing load balancers, they will also be also removed
        from said load balancers
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=0),
                [server('abc', ServerState.ACTIVE, servicenet_address='1.1.1.1', created=0)],
                [LBNode(lb_id=5, address='1.1.1.1', node_id=3,
                        config=LBConfig(port=80))],
                0),
            Convergence(steps=pbag([
                DeleteServer(server_id='abc'),
                RemoveFromLoadBalancer(lb_id=5, node_id=3)
            ])))

    def test_scale_down_building_first(self):
        """
        When scaling down, first we delete building servers, in preference
        to older server.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                [server('abc', ServerState.ACTIVE, created=0),
                 server('def', ServerState.BUILD, created=1),
                 server('ghi', ServerState.ACTIVE, created=2)],
                [],
                0),
            Convergence(
                steps=pbag([DeleteServer(server_id='def')])))

    def test_timeout_building(self):
        """
        Servers that have been building for too long will be deleted and
        replaced.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                [server('slowpoke', ServerState.BUILD, created=0),
                 server('ok', ServerState.ACTIVE, created=0)],
                [],
                3600),
            Convergence(
                steps=pbag([
                    DeleteServer(server_id='slowpoke'),
                    CreateServer(launch_config=pmap())])))

    def test_timeout_replace_only_when_necessary(self):
        """
        If a server is timing out *and* we're over capacity, it will be
        deleted without replacement.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                [server('slowpoke', ServerState.BUILD, created=0),
                 server('old-ok', ServerState.ACTIVE, created=0),
                 server('new-ok', ServerState.ACTIVE, created=3600)],
                [],
                3600),
            Convergence(steps=pbag([DeleteServer(server_id='slowpoke')])))

    def test_converge_active_servers_ignores_servers_to_be_deleted(self):
        """
        Only servers in active that are not being deleted will have their
        load balancers converged.
        """
        desired_lbs = {5: [LBConfig(port=80)]}
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1, desired_lbs=desired_lbs),
                [server('abc', ServerState.ACTIVE, servicenet_address='1.1.1.1', created=0),
                 server('bcd', ServerState.ACTIVE, servicenet_address='2.2.2.2', created=1)],
                [],
                0),
            Convergence(steps=pbag([
                DeleteServer(server_id='abc'),
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('2.2.2.2', LBConfig(port=80))))
            ])))


class RequestConversionTests(SynchronousTestCase):
    """
    Tests for converting ISteps to :obj:`Request`s.
    """

    def test_create_server(self):
        """
        :obj:`CreateServer.as_request` produces a request for creating a server.
        """
        create = CreateServer(launch_config=pmap({'name': 'myserver', 'flavorRef': '1'}))
        self.assertEqual(
            create.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='POST',
                path='servers',
                data=pmap({'name': 'myserver', 'flavorRef': '1'})))

    def test_delete_server(self):
        """
        :obj:`DeleteServer.as_request` produces a request for deleting a server.
        """
        delete = DeleteServer(server_id='abc123')
        self.assertEqual(
            delete.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='DELETE',
                path='servers/abc123'))

    def test_set_metadata_item(self):
        """
        :obj:`SetMetadataItemOnServer.as_request` produces a request for
        setting a metadata item on a particular server.
        """
        meta = SetMetadataItemOnServer(server_id='abc123', key='metadata_key',
                                       value='teapot')
        self.assertEqual(
            meta.as_request(),
            Request(
                service=ServiceType.CLOUD_SERVERS,
                method='PUT',
                path='servers/abc123/metadata/metadata_key',
                data={'meta': {'metadata_key': 'teapot'}}))

    def test_remove_from_load_balancer(self):
        """
        :obj:`RemoveFromLoadBalancer.as_request` produces a request for
        removing a node from a load balancer.
        """
        lbremove = RemoveFromLoadBalancer(
            lb_id='abc123',
            node_id='node1')
        self.assertEqual(
            lbremove.as_request(),
            Request(
                service=ServiceType.CLOUD_LOAD_BALANCERS,
                method='DELETE',
                path='loadbalancers/abc123/node1'))

    def test_change_load_balancer_node(self):
        """
        :obj:`ChangeLoadBalancerNode.as_request` produces a request for
        modifying a load balancer node.
        """
        changenode = ChangeLoadBalancerNode(
            lb_id='abc123',
            node_id='node1',
            condition='DRAINING',
            weight=50,
            type="PRIMARY")
        self.assertEqual(
            changenode.as_request(),
            Request(
                service=ServiceType.CLOUD_LOAD_BALANCERS,
                method='PUT',
                path='loadbalancers/abc123/nodes/node1',
                data={'condition': 'DRAINING',
                      'weight': 50}))


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
        Non-LB steps are not touched by the optimizer.
        """
        steps = pbag([
            AddNodesToLoadBalancer(
                lb_id=5,
                address_configs=s(('1.1.1.1', LBConfig(port=80)))),
            CreateServer(launch_config=pmap({}))
        ])
        self.assertEqual(
            optimize_steps(steps),
            steps)
