"""Tests for convergence."""

from pyrsistent import pmap, pbag

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import (
    converge, _converge_lb_state, Convergence, CreateServer, DeleteServer,
    DesiredGroupState, NovaServer, LBConfig, LBNode,
    AddToLoadBalancer, ChangeLoadBalancerNode, RemoveFromLoadBalancer,
    ACTIVE, ERROR, BUILD)


class ObjectStorageTests(SynchronousTestCase):
    """
    Tests for objects that store data such as :class:`LBConfig`
    """
    def test_lbconfig_default_weight_condition_and_type(self):
        """
        The required values for a LBConfig are just the lb_id and port.  The
        other attributes have default values.
        """
        lb = LBConfig(lb_id=1, port=80)
        self.assertEqual(lb.weight, 1)
        self.assertEqual(lb.condition, "ENABLED")
        self.assertEqual(lb.type, "PRIMARY")


class ConvergeLBStateTests(SynchronousTestCase):
    """
    Tests for :func:`converge_lb_state`
    """
    def test_add_to_lb(self):
        """
        If a desired LB config is not in the set of current configs,
        `converge_lb_state` returns a :class:`AddToLoadBalancer` object
        """
        desired = {(5, 80): LBConfig(lb_id=5, port=80)}
        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_state={},
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [AddToLoadBalancer(loadbalancer_id=5, address='1.1.1.1', port=80,
                               condition="ENABLED", type="PRIMARY", weight=1)])

    def test_change_lb_node(self):
        """
        If a desired LB mapping is in the set of current configs,
        but the configuration is wrong, `converge_lb_state` returns a
        :class:`ChangeLoadBalancerNode` object
        """
        desired = {(5, 80): LBConfig(lb_id=5, port=80)}
        current = {(5, 80): LBNode(node_id=123, address='1.1.1.1',
                                   config=LBConfig(lb_id=5, port=80, weight=5))}

        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_state=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [ChangeLoadBalancerNode(loadbalancer_id=5, node_id=123, weight=1,
                                    condition="ENABLED", type="PRIMARY")])

    def test_remove_lb_node(self):
        """
        If a current lb config is not in the desired set of lb configs,
        `converge_lb_state` returns a :class:`RemoveFromLoadBalancer` object
        """
        current = {(5, 80): LBNode(node_id=123, address='1.1.1.1',
                                   config=LBConfig(lb_id=5, port=80, weight=5))}

        result = _converge_lb_state(desired_lb_state={},
                                    current_lb_state=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(
            list(result),
            [RemoveFromLoadBalancer(loadbalancer_id=5, node_id=123)])

    def test_do_nothing(self):
        """
        If the desired lb state matches the current lb state,
        `converge_lb_state` returns nothing
        """
        desired = {(5, 80): LBConfig(lb_id=5, port=80)}
        current = {(5, 80): LBNode(node_id=123, address='1.1.1.1',
                                   config=LBConfig(lb_id=5, port=80))}

        result = _converge_lb_state(desired_lb_state=desired,
                                    current_lb_state=current,
                                    ip_address='1.1.1.1')
        self.assertEqual(list(result), [])


def server(id, state, created=0):
    """Convenience for creating a :obj:`NovaServer`."""
    return NovaServer(id=id, state=state, created=created)


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
                {},
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
                {},
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
                [server('abc', BUILD)],
                {},
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
                [server('abc', ERROR)],
                {},
                0),
            Convergence(
                steps=pbag([
                    DeleteServer(server_id='abc'),
                    CreateServer(launch_config=pmap()),
                ])))

    def test_scale_down(self):
        """If we have more servers than desired, we delete the oldest."""
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ACTIVE, created=0),
                 server('def', ACTIVE, created=1)],
                {},
                0),
            Convergence(steps=pbag([DeleteServer(server_id='abc')])))

    def test_scale_down_building_first(self):
        """
        When scaling down, first we delete building servers, in preference
        to older server.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=2),
                [server('abc', ACTIVE, created=0),
                 server('def', BUILD, created=1),
                 server('ghi', ACTIVE, created=2)],
                {},
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
                [server('slowpoke', BUILD, created=0),
                 server('ok', ACTIVE, created=0)],
                {},
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
                [server('slowpoke', BUILD, created=0),
                 server('old-ok', ACTIVE, created=0),
                 server('new-ok', ACTIVE, created=3600)],
                {},
                3600),
            Convergence(steps=pbag([DeleteServer(server_id='slowpoke')])))


# time out (delete) building servers
# load balancers!
