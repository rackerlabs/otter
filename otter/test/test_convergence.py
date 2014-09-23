"""Tests for convergence."""

import json

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import succeed

from otter.test.utils import StubTreq2, patch, iMock
from otter.auth import IAuthenticator
from otter.util.http import headers, APIError
from otter.convergence import (
    get_all_server_details, get_scaling_group_servers,
    converge, Convergence, CreateServer, DeleteServer,
    DesiredGroupState, NovaServer,
    ACTIVE, ERROR, BUILD)

from pyrsistent import pmap, pbag


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
        d = get_scaling_group_servers('t', 'a', 's', 'r', sfilter=lambda s: s['id'] % 3 == 0)
        self.assertEqual(
            self.successResultOf(d),
            {'a': [as_servers[0], as_servers[3]], 'b': [as_servers[6]]})


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
