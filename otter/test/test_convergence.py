"""Tests for convergence."""

from pyrsistent import m

from collections import Counter

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import (
    converge, Convergence, CreateServer, DeleteServer,
    AddToLoadBalancer, RemoveFromLoadBalancer, ChangeLoadBalancerNode,
    DesiredGroupState, NovaServer,
    ACTIVE, ERROR, BUILD)


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
                steps=Counter([
                    CreateServer(launch_config=m())])))

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
                steps=Counter([
                    CreateServer(launch_config=m()),
                    CreateServer(launch_config=m())])))

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
            Convergence(
                steps=Counter([])))

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
                steps=Counter([
                    DeleteServer(server_id='abc'),
                    CreateServer(launch_config=m()),
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
            Convergence(
                steps=Counter([
                    DeleteServer(server_id='abc'),
                ])))

    def test_scale_down_building_first(self):
        """
        When scaling down, first we delete building servers, in preference
        to older server.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ACTIVE, created=0),
                 server('def', BUILD, created=1)],
                {},
                0),
            Convergence(
                steps=Counter([
                    DeleteServer(server_id='def')])))


# time out (delete) building servers
# delete building first
# load balancers!
