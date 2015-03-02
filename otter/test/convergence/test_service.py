import time

from effect import (
    ComposedDispatcher, Constant, Effect, Func, ParallelEffects,
    TypeDispatcher, base_dispatcher, sync_perform, sync_performer)
from effect.async import perform_parallel_async
from effect.testing import EQDispatcher

import mock

from pyrsistent import freeze, pmap

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.model import (
    CLBDescription, CLBNode, NovaServer, ServerState)
from otter.convergence.service import (
    ConvergenceStarter,
    Converger, determine_active, execute_convergence, mark_divergent,
    server_to_json)
from otter.http import service_request
from otter.models.intents import (
    GetScalingGroupInfo, ModifyGroupState, perform_modify_group_state)
from otter.models.interface import GroupState
from otter.test.convergence.test_planning import server
from otter.test.utils import (
    FakePartitioner, LockMixin,
    mock_group, mock_log,
    transform_eq)
from otter.util.fp import eref_dispatcher
from otter.util.zk import CreateOrSet


class MarkDivergentTests(SynchronousTestCase):
    """Tests for :func:`mark_divergent`."""

    def test_marks_dirty(self):
        """
        returns an effect which will create or set a node relative to
        ``CONVERGENCE_DIRTY_PATH``.
        """
        eff = mark_divergent('tenant', 'group')
        self.assertEqual(
            eff,
            Effect(CreateOrSet(path='/groups/divergent/tenant_group',
                               content='dirty')))


class ConvergenceStarterTests(SynchronousTestCase):
    """Tests for :obj:`ConvergenceStarter`."""

    def test_start_convergence(self):
        svc = ConvergenceStarter('my-dispatcher')
        log = mock_log()

        def perform(dispatcher, eff):
            return succeed((dispatcher, eff))
        d = svc.start_convergence(log, 'tenant', 'group', perform=perform)
        self.assertEqual(
            self.successResultOf(d),
            ('my-dispatcher',
             Effect(CreateOrSet(path='/groups/divergent/tenant_group',
                                content='dirty'))))


class ConvergerTests(SynchronousTestCase):
    """
    converge_one_non_concurrently
    - early-out if in currently_converging
    - adds the group to currently_converging
    - remove from currently converging set
    """

    def setUp(self):
        self.kz_client = mock.Mock(Lock=LockMixin().mock_lock())
        self.dispatcher = object()
        self.log = mock_log()
        self.buckets = range(10)

        def pfactory(log, callable):
            self.fake_partitioner = FakePartitioner(log, callable)
            return self.fake_partitioner

        self.converger = Converger(self.log, self.dispatcher, self.buckets,
                                   pfactory)
        self.state = GroupState('tenant-id', 'group-id', 'group-name',
                                {}, {}, None, {}, False)
        self.group = mock_group(self.state, 'tenant-id', 'group-id')
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}

    def test_converge_one(self):
        """
        """
        eff = self.converger.converge_one('tenant-id', 'group-id', 0)
        dispatcher = ComposedDispatcher([
            EQDispatcher({
                Func(time.time): 100,
                GetScalingGroupInfo(tenant_id='tenant-id',
                                    group_id='group-id'):
                    (self.group, self.state, self.lc)
            }),
            eref_dispatcher,
            base_dispatcher,
        ])
        result = sync_perform(dispatcher, eff)


class ExecuteConvergenceTests(SynchronousTestCase):
    """Tests for :func:`execute_convergence`."""

    def setUp(self):
        self.tenant_id = 'tenant-id'
        self.group_id = 'group-id'
        self.state = GroupState(self.tenant_id, self.group_id, 'group-name',
                                {}, {}, None, {}, False, desired=2)
        self.group = mock_group(self.state, self.tenant_id, self.group_id)
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}
        self.desired_lbs = freeze({23: [CLBDescription(lb_id='23', port=80)]})
        self.servers = [
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       created=0,
                       image_id='image',
                       flavor_id='flavor',
                       servicenet_address='10.0.0.1',
                       desired_lbs=self.desired_lbs),
            NovaServer(id='b',
                       state=ServerState.ACTIVE,
                       created=0,
                       image_id='image',
                       flavor_id='flavor',
                       servicenet_address='10.0.0.2',
                       desired_lbs=self.desired_lbs)
        ]

    def _get_dispatcher(self, expected_intents=None, additional=None):
        if expected_intents is None:
            gsgi = GetScalingGroupInfo(tenant_id='tenant-id',
                                       group_id='group-id')
            gsgi_result = (self.group, self.state, self.lc)
            expected_intents = {gsgi: gsgi_result}
        if additional is not None:
            expected_intents.update(additional)
        return ComposedDispatcher([
            EQDispatcher(expected_intents),
            TypeDispatcher({
                ParallelEffects: perform_parallel_async,
                ModifyGroupState: perform_modify_group_state,
            }),
            base_dispatcher,
        ])

    def _get_gacd_func(self, group_id):
        def get_all_convergence_data(grp_id):
            self.assertEqual(grp_id, group_id)
            return Effect(Constant((tuple(self.servers), ())))
        return get_all_convergence_data

    def test_no_steps(self):
        """
        If state of world matches desired, no steps are executed, but the
        `active` servers are still updated.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        for s in self.servers:
            s.desired_lbs = pmap()

        tscope_eff = execute_convergence(self.tenant_id, self.group_id, log,
                                         get_all_convergence_data=gacd)
        self.assertEqual(tscope_eff.intent.tenant_id, self.tenant_id)
        self.assertEqual(tscope_eff.callbacks, [])
        expected_active = {'a': server_to_json(self.servers[0]),
                           'b': server_to_json(self.servers[1])}
        result = sync_perform(self._get_dispatcher(), tscope_eff.intent.effect)
        self.assertEqual(self.group.modify_state_values[-1].active,
                         expected_active)
        self.assertEqual(result, [])

    def test_success(self):
        """
        Executes optimized steps if state of world does not match desired and
        returns the result of all the steps.
        """
        # The scenario: We have two servers but they're not in the LBs
        # yet. convergence should add them to the LBs.
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        tscope_eff = execute_convergence(self.tenant_id, self.group_id, log,
                                         get_all_convergence_data=gacd)
        self.assertEqual(tscope_eff.intent.tenant_id, self.tenant_id)
        self.assertEqual(tscope_eff.callbacks, [])
        expected_req = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            'loadbalancers/23/nodes',
            data=transform_eq(
                freeze,
                pmap({
                    'nodes': transform_eq(
                        lambda nodes: set(freeze(nodes)),
                        set([pmap({'weight': 1, 'type': 'PRIMARY',
                                   'port': 80,
                                   'condition': 'ENABLED',
                                   'address': '10.0.0.2'}),
                             pmap({'weight': 1, 'type': 'PRIMARY',
                                   'port': 80,
                                   'condition': 'ENABLED',
                                   'address': '10.0.0.1'})]))})),
            success_pred=mock.ANY)
        expected_intents = {expected_req.intent: 'stuff'}
        result = sync_perform(
            self._get_dispatcher(additional=expected_intents),
            tscope_eff.intent.effect)
        self.assertEqual(self.group.modify_state_values[-1].active, {})
        self.assertEqual(result, ['stuff'])

    def test_first_error_extraction(self):
        """
        If the GetScalingGroupInfo effect fails, its exception is raised
        directly, without the FirstError wrapper.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        for s in self.servers:
            s.desired_lbs = pmap()

        @sync_performer
        def perform_gsgi(dispatcher, intent):
            raise RuntimeError('foo')

        tscope_eff = execute_convergence(self.tenant_id, self.group_id, log,
                                         get_all_convergence_data=gacd)

        dispatcher = ComposedDispatcher([
            TypeDispatcher({GetScalingGroupInfo: perform_gsgi}),
            self._get_dispatcher(None)])
        e = self.assertRaises(
            RuntimeError,
            sync_perform, dispatcher, tscope_eff.intent.effect)
        self.assertEqual(str(e), 'foo')


class DetermineActiveTests(SynchronousTestCase):
    """Tests for :func:`determine_active`."""

    def test_nothing(self):
        """No input means no active servers."""
        self.assertEqual(determine_active([], []), [])

    def test_active(self):
        """Built servers with no desired LBs are active."""
        servers = [server('id1', ServerState.ACTIVE),
                   server('id2', ServerState.BUILD)]
        self.assertEqual(determine_active(servers, []), servers[:1])

    def test_lb_pending(self):
        """
        When a server should be in a LB but it's not, it's not active.
        """
        desired_lbs = pmap({'foo': [CLBDescription(lb_id='foo', port=80)]})
        lb_nodes = [
            CLBNode(node_id='x',
                    description=CLBDescription(lb_id='foo', port=80),
                    address='1.1.1.3')]
        servers = [
            server('id1', ServerState.ACTIVE, servicenet_address='1.1.1.1',
                   desired_lbs=desired_lbs),
            server('id2', ServerState.ACTIVE, servicenet_address='1.1.1.2',
                   desired_lbs=desired_lbs),
            server('id3', ServerState.ACTIVE, servicenet_address='1.1.1.3',
                   desired_lbs=desired_lbs)]
        self.assertEqual(determine_active(servers, lb_nodes), servers[2:])

    def test_multiple_lb_pending(self):
        """
        When a server needs to be added to multiple LBs, it's only counted
        once.
        """
        lb_nodes = [
            CLBNode(node_id='1',
                    description=CLBDescription(lb_id='foo', port=1),
                    address='1.1.1.1'),
            CLBNode(node_id='2',
                    description=CLBDescription(lb_id='foo', port=2),
                    address='1.1.1.1'),
            CLBNode(node_id='3',
                    description=CLBDescription(lb_id='bar', port=3),
                    address='1.1.1.1'),
            CLBNode(node_id='4',
                    description=CLBDescription(lb_id='bar', port=4),
                    address='1.1.1.1'),
        ]
        desired_lbs = pmap({'foo': [CLBDescription(lb_id='foo', port=1),
                                    CLBDescription(lb_id='foo', port=2)],
                            'bar': [CLBDescription(lb_id='bar', port=3),
                                    CLBDescription(lb_id='bar', port=4)]})
        servers = [
            server('id1', ServerState.ACTIVE, servicenet_address='1.1.1.1',
                   desired_lbs=desired_lbs),
            server('id2', ServerState.ACTIVE, servicenet_address='1.1.1.2',
                   desired_lbs=desired_lbs)
        ]
        self.assertEqual(determine_active(servers, lb_nodes), servers[:1])
