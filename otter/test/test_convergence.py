"""Tests for convergence."""

from twisted.trial.unittest import SynchronousTestCase

from otter.convergence import (
    converge, Convergence as Cnvgnc, CreateServer, DeleteServer,
    AddToLoadBalancer, RemoveFromLoadBalancer, ChangeLoadBalancerNode,
    DesiredGroupState as DSG, NovaServer)



def DesiredGroupState(launch_config, desired):
    return DSG(id=1, launch_config=launch_config, desired=desired)


def server(id, state, created=0):
    return NovaServer(id=id, state=state, created=created)


def Convergence(steps):
    return Cnvgnc(group_id=1, steps=steps)


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
                steps=[
                    CreateServer(launch_config={})]))

    def test_converge_give_me_multiple_server(self):
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
                steps=[
                    CreateServer(launch_config={}),
                    CreateServer(launch_config={})]))

    def test_count_building_as_meeting_capacity(self):
        """
        No servers are created if there are building servers that sum with
        active servers to meet capacity.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', 'BUILDING')],
                {},
                0),
            Convergence(
                steps=[]))

    def test_delete_nodes_in_error_state(self):
        """
        If a server we created enters error state, it will be deleted if
        necessary, and replaced.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', 'ERROR')],
                {},
                0),
            Convergence(
                steps=[
                    DeleteServer(server_id='abc'),
                    CreateServer(launch_config={}),
                ]))

    def test_scale_down(self):
        """If we have more servers than desired, we delete some."""
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', 'ACTIVE', created=0),
                 server('def', 'ACTIVE', created=1)],
                {},
                0),
            Convergence(
                steps=[
                    DeleteServer(server_id='abc'),
                ]))

# time out (delete) building servers
# delete building first
# load balancers!
