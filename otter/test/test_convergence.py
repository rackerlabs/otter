"""Tests for convergence."""

import json

from effect import Effect
from effect.testing import StubIntent, resolve_stubs

from twisted.trial.unittest import SynchronousTestCase
from twisted.internet.task import Clock
from twisted.internet.defer import succeed

from otter.constants import ServiceType
from otter.test.utils import StubTreq2, patch
from otter.util.http import APIError
from otter.convergence import (
    _converge_lb_state,
    get_all_server_details, get_scaling_group_servers,
    converge, Convergence, CreateServer, DeleteServer,
    RemoveFromLoadBalancer, ChangeLoadBalancerNode, AddNodesToLoadBalancer,
    DesiredGroupState, NovaServer, Request, LBConfig, LBNode,
    ACTIVE, ERROR, BUILD,
    ServiceType, NodeCondition, NodeType, optimize_steps)

from pyrsistent import pmap, pbag, s


class Sequence(object):
    """
    An Effect intent that returns a different result each time it's performed.
    """
    def __init__(self, responses):
        """
        :param list responses: Responses to return in sequence. Instances of
            exception will be raised.
        """
        self.responses = responses
        self._index = 0

    def perform_effect(self, dispatcher):
        """Return or raise the next result in sequence."""
        index = self._index
        self._index += 1
        response = self.responses[index]
        if isinstance(response, Exception):
            raise response
        else:
            return response


def _request(requests):
    def request(service_type, method, url, retry):
        responses = requests.get((service_type, method, url, retry))
        if responses is None:
            raise KeyError("{} not in {}".format((method, url), requests.keys()))
        if not isinstance(responses, list):
            responses = [responses]
        return Effect(StubIntent(Sequence(responses)))
    return request


class GetAllServerDetailsTests(SynchronousTestCase):
    """
    Tests for :func:`get_all_server_details`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail?limit=10', True)
        self.servers = [{'id': i} for i in range(9)]

    def test_get_all_less_limit(self):
        """
        `get_all_server_details` will not fetch again if first get returns
        results with size < limit
        """
        request = _request({self.req: {'servers': self.servers}})
        eff = get_all_server_details(request, limit=10)
        self.assertEqual(resolve_stubs(eff), self.servers)

    def test_get_all_above_limit(self):
        """
        `get_all_server_details` will fetch again until batch returned has size < limit
        """
        servers = [{'id': i} for i in range(19)]

        req2 = (ServiceType.CLOUD_SERVERS, 'GET',
                'servers/detail?limit=10&marker=9', True)
        request = _request({self.req: {'servers': servers[:10]},
                                 req2: {'servers': servers[10:]}})
        eff = get_all_server_details(request, limit=10)
        self.assertEqual(resolve_stubs(eff), servers)


class GetScalingGroupServersTests(SynchronousTestCase):
    """
    Tests for :func:`get_scaling_group_servers`
    """

    def setUp(self):
        """Save basic reused data."""
        self.req = (ServiceType.CLOUD_SERVERS, 'GET',
                    'servers/detail?limit=100', True)

    def test_filters_no_metadata(self):
        """
        Does not include servers which do not have metadata in it
        """
        servers = [{'id': i} for i in range(10)]
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(resolve_stubs(eff), {})

    def test_filters_no_as_metadata(self):
        """
        Does not include servers which have metadata but does not have AS info in it
        """
        servers = [{'id': i, 'metadata': {}} for i in range(10)]
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(resolve_stubs(eff), {})

    def test_returns_as_servers(self):
        """
        Returns servers with AS metadata in it grouped by scaling group ID
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': 10}])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request)
        self.assertEqual(
            resolve_stubs(eff),
            {'a': as_servers[:5] + [as_servers[-1]], 'b': as_servers[5:8]})

    def test_filters_on_user_criteria(self):
        """
        Considers user provided filter if provided
        """
        as_servers = (
            [{'metadata': {'rax:auto_scaling_group_id': 'a'}, 'id': i} for i in range(5)] +
            [{'metadata': {'rax:auto_scaling_group_id': 'b'}, 'id': i} for i in range(5, 8)])
        servers = as_servers + [{'metadata': 'junk'}] * 3
        request = _request({self.req: {'servers': servers}})
        eff = get_scaling_group_servers(request, server_predicate=lambda s: s['id'] % 3 == 0)
        self.assertEqual(
            resolve_stubs(eff),
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

    def test_lbconfig_not_cmp_draining(self):
        """
        :obj:`LBConfig.draining_timeout` is excluded from comparison
        """
        self.assertEqual(LBConfig(port=80, draining_timeout=2.4),
                         LBConfig(port=80, draining_timeout=5.4))


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

    def test_delete_error_state_servers_with_lb_nodes(self):
        """
        If a server we created enters error state and it is attached to one
        or more load balancers, it will be removed from its load balancers
        as well as get deleted.
        """
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1),
                [server('abc', ERROR, servicenet_address='1.1.1.1')],
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
                [server('abc', ACTIVE, created=0),
                 server('def', ACTIVE, created=1)],
                {},
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
                [server('abc', ACTIVE, servicenet_address='1.1.1.1', created=0)],
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

    def test_converge_active_servers_ignores_servers_to_be_deleted(self):
        """
        Only servers in active that are not being deleted will have their
        load balancers converged.
        """
        desired_lbs = {5: [LBConfig(port=80)]}
        self.assertEqual(
            converge(
                DesiredGroupState(launch_config={}, desired=1, desired_lbs=desired_lbs),
                [server('abc', ACTIVE, servicenet_address='1.1.1.1', created=0),
                 server('bcd', ACTIVE, servicenet_address='2.2.2.2', created=1)],
                [],
                0),
            Convergence(steps=pbag([
                DeleteServer(server_id='abc'),
                AddNodesToLoadBalancer(
                    lb_id=5,
                    address_configs=s(('2.2.2.2', LBConfig(port=80))))
            ])))

# time out (delete) building servers


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
