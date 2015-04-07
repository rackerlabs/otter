from effect import (
    ComposedDispatcher, Constant, Effect, Error, Func, ParallelEffects,
    TypeDispatcher, base_dispatcher, sync_perform)
from effect.async import perform_parallel_async
from effect.ref import ReadReference, Reference, reference_dispatcher
from effect.testing import EQDispatcher, EQFDispatcher, SequenceDispatcher

from kazoo.exceptions import BadVersionError
from kazoo.recipe.partitioner import PartitionState

import mock

from pyrsistent import freeze, pbag, pmap, pset, s

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import TenantScope, service_request
from otter.constants import CONVERGENCE_DIRTY_DIR, ServiceType
from otter.convergence.model import (
    CLBDescription, CLBNode, NovaServer, ServerState, StepResult)
from otter.convergence.service import (
    ConcurrentError,
    ConvergenceStarter,
    Converger,
    converge_all_groups,
    converge_one_group,
    determine_active, execute_convergence, get_my_divergent_groups,
    non_concurrently)
from otter.convergence.steps import ConvergeLater
from otter.models.intents import (
    DeleteGroup,
    GetScalingGroupInfo,
    ModifyGroupState,
    perform_modify_group_state)
from otter.models.interface import GroupState, NoSuchScalingGroupError
from otter.test.convergence.test_planning import server
from otter.test.util.test_zk import ZNodeStatStub
from otter.test.utils import (
    CheckFailureValue, FakePartitioner, IsBoundWith,
    TestStep,
    matches,
    mock_group, mock_log,
    raise_,
    test_dispatcher,
    transform_eq)
from otter.util.zk import CreateOrSet, DeleteNode, GetChildren, GetStat


class ConvergenceStarterTests(SynchronousTestCase):
    """Tests for :obj:`ConvergenceStarter`."""

    def test_start_convergence(self):
        """Starting convergence marks dirty and logs a message."""
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
        log.msg.assert_called_once_with(
            'mark-dirty-success', tenant_id='tenant', group_id='group')

    def test_error_marking_dirty(self):
        """An error is logged when marking dirty fails."""
        svc = ConvergenceStarter('my-dispatcher')
        log = mock_log()

        def perform(dispatcher, eff):
            return fail(RuntimeError('oh no'))
        d = svc.start_convergence(log, 'tenant', 'group', perform=perform)
        self.assertEqual(self.successResultOf(d), None)
        log.err.assert_called_once_with(
            CheckFailureValue(RuntimeError('oh no')),
            'mark-dirty-failure', tenant_id='tenant', group_id='group')


class ConvergerTests(SynchronousTestCase):
    """Tests for :obj:`Converger`."""

    def setUp(self):
        self.log = mock_log()
        self.buckets = range(10)

    def _converger(self, converge_all_groups, dispatcher=None):
        if dispatcher is None:
            dispatcher = _get_dispatcher()
        return Converger(
            self.log, dispatcher, self.buckets,
            self._pfactory, converge_all_groups=converge_all_groups)

    def _pfactory(self, log, callable):
        self.fake_partitioner = FakePartitioner(log, callable)
        return self.fake_partitioner

    def test_buckets_acquired(self):
        """
        When buckets are allocated, the result of converge_all_groups is
        performed.
        """
        def converge_all_groups(log, currently_converging, _my_buckets,
                                all_buckets, divergent_flags):
            return Effect(
                ('converge-all', log, currently_converging, _my_buckets,
                 all_buckets, divergent_flags))

        my_buckets = [0, 5]
        sequence = SequenceDispatcher([
            (GetChildren(CONVERGENCE_DIRTY_DIR), lambda i: ['flag1', 'flag2']),

            (('converge-all',
              matches(IsBoundWith(otter_service='converger')),
              transform_eq(lambda cc: cc is converger.currently_converging,
                           True),
              my_buckets,
              self.buckets,
              ['flag1', 'flag2']),
             lambda i: 'foo')
        ])

        converger = self._converger(converge_all_groups, dispatcher=sequence)

        result = self.fake_partitioner.got_buckets(my_buckets)
        self.assertEqual(self.successResultOf(result), 'foo')
        self.assertEqual(sequence.sequence, [])

    def test_buckets_acquired_errors(self):
        """
        Errors raised from performing the converge_all_groups effect are
        logged, and None is the ultimate result.
        """
        def converge_all_groups(log, currently_converging, _my_buckets,
                                all_buckets, divergent_flags):
            return Effect('converge-all')

        sequence = SequenceDispatcher([
            (GetChildren(CONVERGENCE_DIRTY_DIR), lambda i: ['flag1', 'flag2']),
            ('converge-all', lambda i: raise_(RuntimeError('foo')))
        ])
        self._converger(converge_all_groups, dispatcher=sequence)

        result = self.fake_partitioner.got_buckets([0])
        self.assertEqual(self.successResultOf(result), None)
        self.log.err.assert_called_once_with(
            CheckFailureValue(RuntimeError('foo')),
            'converge-all-groups-error', otter_service='converger')
        self.assertEqual(sequence.sequence, [])

    def test_divergent_changed_not_acquired(self):
        """
        When notified that divergent groups have changed and we have not
        acquired our buckets, nothing is done.
        """
        dispatcher = SequenceDispatcher([])  # "nothing happens"
        converger = self._converger(lambda *a, **kw: 1 / 0,
                                    dispatcher=dispatcher)
        converger.divergent_changed(['group1', 'group2'])

    def test_divergent_changed_not_ours(self):
        """
        When notified that divergent groups have changed but they're not ours,
        nothing is done.
        """
        dispatcher = SequenceDispatcher([])  # "nothing happens"
        converger = self._converger(lambda *a, **kw: 1 / 0,
                                    dispatcher=dispatcher)
        self.fake_partitioner.current_state = PartitionState.ACQUIRED
        converger.divergent_changed(['group1', 'group2'])

    def test_divergent_changed(self):
        """
        When notified that divergent groups have changed, and one of the groups
        is associated with a bucket assigned to us, convergence is triggered,
        and the list of child nodes is passed on to
        :func:`converge_all_groups`.
        """
        def converge_all_groups(log, currently_converging, _my_buckets,
                                all_buckets, divergent_flags):
            return Effect(('converge-all-groups', divergent_flags))
        dispatcher = SequenceDispatcher([
            (('converge-all-groups', ['group1', 'group2']),
             lambda i: None)
        ])
        converger = self._converger(converge_all_groups, dispatcher=dispatcher)
        # sha1('group1') % 10 == 3
        self.fake_partitioner.current_state = PartitionState.ACQUIRED
        self.fake_partitioner.my_buckets = [3]
        converger.divergent_changed(['group1', 'group2'])
        self.assertEqual(dispatcher.sequence, [])  # All side-effects performed


class ConvergeOneGroupTests(SynchronousTestCase):
    """Tests for :func:`converge_one_group`."""

    def setUp(self):
        self.log = mock_log()
        self.tenant_id = 'tenant-id'
        self.group_id = 'g1'
        self.version = 5
        self.deletions = []
        self.dispatcher = ComposedDispatcher([
            EQFDispatcher([
                (DeleteNode(path='/groups/divergent/tenant-id_g1',
                            version=self.version),
                 lambda i: self.deletions.append(True))
            ]),
            _get_dispatcher(),
        ])

    def test_success(self):
        """
        runs execute_convergence and returns None, then deletes the dirty flag.
        """
        calls = []

        def execute_convergence(tenant_id, group_id, log):
            def p():
                calls.append((tenant_id, group_id, log))
                return StepResult.SUCCESS
            return Effect(Func(p))

        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)
        self.assertEqual(
            calls,
            [(self.tenant_id, self.group_id,
              matches(IsBoundWith(tenant_id=self.tenant_id,
                                  group_id=self.group_id)))])
        self.assertEqual(self.deletions, [True])
        self.log.msg.assert_any_call(
            'mark-clean-success',
            tenant_id=self.tenant_id, group_id=self.group_id)

    def test_non_concurrent(self):
        """
        Won't run execute_convergence if it's already running for the same
        group ID.
        """
        calls = []

        def execute_convergence(tenant_id, group_id, log):
            return Effect(Func(lambda: calls.append('should not be run')))

        currently_converging = Reference(pset([self.group_id]))
        eff = converge_one_group(
            self.log, currently_converging, self.tenant_id,
            self.group_id, self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)
        self.assertEqual(calls, [])
        self.assertEqual(self.log.err.mock_calls, [])
        self.assertEqual(self.deletions, [])

    def test_no_scaling_group(self):
        """
        When the scaling group disappears, a fatal error is logged and the
        dirty flag is cleaned up.
        """
        def execute_convergence(tenant_id, group_id, log):
            return Effect(Error(NoSuchScalingGroupError(tenant_id, group_id)))

        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)

        self.log.err.assert_any_call(
            None,
            'converge-fatal-error',
            tenant_id=self.tenant_id, group_id=self.group_id)

        self.assertEqual(self.deletions, [True])
        self.log.msg.assert_any_call(
            'mark-clean-success',
            tenant_id=self.tenant_id, group_id=self.group_id)

    def test_unexpected_errors(self):
        """
        Unexpected exceptions log a non-fatal error and don't clean up the
        dirty flag.
        """
        def execute_convergence(tenant_id, group_id, log):
            return Effect(Error(RuntimeError('uh oh!')))

        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)
        self.log.err.assert_any_call(
            None,
            'converge-non-fatal-error',
            tenant_id=self.tenant_id, group_id=self.group_id)
        self.assertEqual(self.deletions, [])

    def test_delete_node_version_mismatch(self):
        """
        When the version of the dirty flag changes during a call to
        converge_one_group, and DeleteNode raises a BadVersionError, the error
        is logged and nothing else is cleaned up.
        """
        dispatcher = ComposedDispatcher([
            EQFDispatcher([
                (DeleteNode(path='/groups/divergent/tenant-id_g1',
                            version=self.version),
                 lambda i: raise_(BadVersionError()))
            ]),
            _get_dispatcher(),
            ])

        def execute_convergence(tenant_id, group_id, log):
            return Effect(Constant(StepResult.SUCCESS))

        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(dispatcher, eff)
        self.assertEqual(result, None)
        self.log.err.assert_any_call(
            CheckFailureValue(BadVersionError()),
            'mark-clean-failure',
            tenant_id=self.tenant_id, group_id=self.group_id,
            dirty_version=5,
            path='/groups/divergent/tenant-id_g1')

    def test_retry(self):
        """
        When execute_convergence returns RETRY, the divergent flag is not
        deleted.
        """
        def execute_convergence(tenant_id, group_id, log):
            return Effect(Constant(StepResult.RETRY))
        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)
        self.assertEqual(self.deletions, [])

    def test_failure(self):
        """
        When execute_convergence returns FAILURE, the divergent flag is
        deleted.
        """
        def execute_convergence(tenant_id, group_id, log):
            return Effect(Constant(StepResult.FAILURE))
        eff = converge_one_group(
            self.log, Reference(pset()), self.tenant_id, self.group_id,
            self.version,
            execute_convergence=execute_convergence)
        result = sync_perform(self.dispatcher, eff)
        self.assertEqual(result, None)
        self.assertEqual(self.deletions, [True])


class ConvergeAllGroupsTests(SynchronousTestCase):
    """Tests for :func:`converge_all_groups`."""

    def setUp(self):
        self.log = mock_log()
        self.currently_converging = Reference(pset())
        self.my_buckets = [1, 6]
        self.all_buckets = range(10)
        self.group_infos = [
            {'tenant_id': '00', 'group_id': 'g1',
             'dirty-flag': '/groups/divergent/00_g1'},
            {'tenant_id': '01', 'group_id': 'g2',
             'dirty-flag': '/groups/divergent/01_g2'}
        ]

    def _converge_all_groups(self, flags):
        return converge_all_groups(
            self.log, self.currently_converging, self.my_buckets,
            self.all_buckets,
            flags,
            converge_one_group=self._converge_one_group)

    def _converge_one_group(self, log, currently_converging, tenant_id,
                            group_id, version):
        return Effect(('converge', tenant_id, group_id, version))

    def test_converge_all_groups(self):
        """
        Fetches divergent groups and runs converge_one_group for each one
        needing convergence.
        """
        eff = self._converge_all_groups(['00_g1', '01_g2'])

        sequence = SequenceDispatcher([
            (ReadReference(ref=self.currently_converging),
             lambda i: pset()),

            (GetStat(path='/groups/divergent/00_g1'),
             lambda i: ZNodeStatStub(version=1)),
            (TenantScope(
                Effect(('converge', '00', 'g1', 1)),
                '00'),
             lambda tscope: tscope.effect),
            (('converge', '00', 'g1', 1),
             lambda i: 'converged one!'),

            (GetStat(path='/groups/divergent/01_g2'),
             lambda i: ZNodeStatStub(version=5)),
            (TenantScope(
                Effect(('converge', '01', 'g2', 5)),
                '01'),
             lambda tscope: tscope.effect),
            (('converge', '01', 'g2', 5),
             lambda i: 'converged two!'),
        ])
        dispatcher = ComposedDispatcher([sequence, test_dispatcher()])

        self.assertEqual(
            sync_perform(dispatcher, eff),
            ['converged one!', 'converged two!'])
        self.log.msg.assert_called_once_with(
            'converge-all-groups',
            group_infos=self.group_infos,
            currently_converging=[])
        self.assertEqual(sequence.sequence, [])  # All side-effects performed

    def test_filter_out_currently_converging(self):
        """
        If a group is already being converged, its dirty flag is not statted
        convergence is not run for it.
        """
        eff = self._converge_all_groups(['00_g1', '01_g2'])
        sequence = SequenceDispatcher([
            (ReadReference(ref=self.currently_converging),
             lambda i: pset(['g1'])),

            (GetStat(path='/groups/divergent/01_g2'),
             lambda i: ZNodeStatStub(version=5)),
            (TenantScope(
                Effect(('converge', '01', 'g2', 5)),
                '01'),
             lambda tscope: tscope.effect),
            (('converge', '01', 'g2', 5),
             lambda i: 'converged two!'),
        ])
        dispatcher = ComposedDispatcher([sequence, test_dispatcher()])

        self.assertEqual(sync_perform(dispatcher, eff), ['converged two!'])
        self.log.msg.assert_called_once_with(
            'converge-all-groups',
            group_infos=[self.group_infos[1]],
            currently_converging=['g1'])
        self.assertEqual(sequence.sequence, [])  # All side-effects performed

    def test_no_log_on_no_groups(self):
        """When there's no work, no log message is emitted."""
        def converge_one_group(log, currently_converging, tenant_id, group_id,
                               version):
            1 / 0

        result = converge_all_groups(
            self.log, self.currently_converging, self.my_buckets,
            self.all_buckets,
            [],
            converge_one_group=converge_one_group)
        self.assertEqual(sync_perform(_get_dispatcher(), result), None)
        self.assertEqual(self.log.msg.mock_calls, [])


class GetMyDivergentGroupsTests(SynchronousTestCase):

    def test_get_my_divergent_groups(self):
        """
        :func:`get_my_divergent_groups` returns structured information about
        divergent groups that are associated with the given buckets.
        """
        # sha1('00') % 10 is 6, sha1('01') % 10 is 1.
        result = get_my_divergent_groups(
            [6], range(10), ['00_gr1', '00_gr2', '01_gr3'])
        self.assertEqual(
            result,
            [{'tenant_id': '00', 'group_id': 'gr1',
              'dirty-flag': '/groups/divergent/00_gr1'},
             {'tenant_id': '00', 'group_id': 'gr2',
              'dirty-flag': '/groups/divergent/00_gr2'}])


def _get_dispatcher():
    return ComposedDispatcher([
        TypeDispatcher({
            ParallelEffects: perform_parallel_async,
        }),
        reference_dispatcher,
        base_dispatcher,
    ])


class NonConcurrentlyTests(SynchronousTestCase):
    """Tests for :func:`non_concurrently`."""

    def setUp(self):
        self.locks = Reference(pset())

    def _get_locks(self):
        """Get the locks set."""
        return sync_perform(_get_dispatcher(), self.locks.read())

    def _add_lock(self, value):
        """Add an item to the locks set."""
        return sync_perform(_get_dispatcher(),
                            self.locks.modify(lambda cc: cc.add(value)))

    def test_success(self):
        """
        :func:`non_concurrently` returns the result of the passed effect, and
        adds the ``key`` to the ``locks`` while executing.
        """
        dispatcher = _get_dispatcher()

        def execute_stuff():
            self.assertEqual(self._get_locks(), pset(['the-key']))
            return 'foo'

        eff = Effect(Func(execute_stuff))

        non_c_eff = non_concurrently(self.locks, 'the-key', eff)
        self.assertEqual(sync_perform(dispatcher, non_c_eff), 'foo')
        # after the effect completes, its lock is released
        self.assertEqual(self._get_locks(), pset([]))

    def test_refuses_concurrency(self):
        """
        :func:`non_concurrently` raises :obj:`ConcurrentError` when the key is
        already locked.
        """
        self._add_lock('the-key')
        eff = Effect(Error(RuntimeError('foo')))
        non_c_eff = non_concurrently(self.locks, 'the-key', eff)
        self.assertRaises(
            ConcurrentError,
            sync_perform, _get_dispatcher(), non_c_eff)
        self.assertEqual(self._get_locks(), pset(['the-key']))

    def test_cleans_up_on_exception(self):
        """
        When the effect results in error, the key is still removed from the
        locked set.
        """
        dispatcher = _get_dispatcher()
        eff = Effect(Error(RuntimeError('foo!')))
        non_c_eff = non_concurrently(self.locks, 'the-key', eff)
        e = self.assertRaises(RuntimeError, sync_perform, dispatcher,
                              non_c_eff)
        self.assertEqual(str(e), 'foo!')
        self.assertEqual(self._get_locks(), pset([]))


class ExecuteConvergenceTests(SynchronousTestCase):
    """Tests for :func:`execute_convergence`."""

    def setUp(self):
        self.tenant_id = 'tenant-id'
        self.group_id = 'group-id'
        self.state = GroupState(self.tenant_id, self.group_id, 'group-name',
                                {}, {}, None, {}, False, desired=2)
        self.group = mock_group(self.state, self.tenant_id, self.group_id)
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}
        self.desired_lbs = s(CLBDescription(lb_id='23', port=80))
        self.servers = [
            NovaServer(id='a',
                       state=ServerState.ACTIVE,
                       created=0,
                       image_id='image',
                       flavor_id='flavor',
                       servicenet_address='10.0.0.1',
                       desired_lbs=self.desired_lbs,
                       links=freeze([{'href': 'link1', 'rel': 'self'}])),
            NovaServer(id='b',
                       state=ServerState.ACTIVE,
                       created=0,
                       image_id='image',
                       flavor_id='flavor',
                       servicenet_address='10.0.0.2',
                       desired_lbs=self.desired_lbs,
                       links=freeze([{'href': 'link2', 'rel': 'self'}]))
        ]
        gsgi = GetScalingGroupInfo(tenant_id='tenant-id',
                                   group_id='group-id')
        self.gsgi = gsgi
        self.manifest = {  # Many details elided!
            'state': self.state,
            'launchConfiguration': self.lc,
            'status': 'ACTIVE'
        }
        gsgi_result = (self.group, self.manifest)
        self.expected_intents = [(gsgi, gsgi_result)]

    def _get_dispatcher(self, expected_intents=None):
        if expected_intents is None:
            expected_intents = self.expected_intents
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
        `active` servers are still updated, and SUCCESS is the return value.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        for serv in self.servers:
            serv.desired_lbs = pset()
        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  get_all_convergence_data=gacd)
        expected_active = {
            'a': {'id': 'a', 'links': [{'href': 'link1', 'rel': 'self'}]},
            'b': {'id': 'b', 'links': [{'href': 'link2', 'rel': 'self'}]}
        }
        result = sync_perform(self._get_dispatcher(), eff)
        self.assertEqual(self.group.modify_state_values[-1].active,
                         expected_active)
        self.assertEqual(result, StepResult.SUCCESS)

    def test_success(self):
        """
        Executes optimized steps if state of world does not match desired and
        returns the result of all the steps.
        """
        # The scenario: We have two servers but they're not in the LBs
        # yet. convergence should add them to the LBs.
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  get_all_convergence_data=gacd)
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
        expected_intents = self.expected_intents + [
            (expected_req.intent, 'successful response')]
        result = sync_perform(self._get_dispatcher(expected_intents), eff)
        self.assertEqual(self.group.modify_state_values[-1].active, {})
        self.assertEqual(result, StepResult.SUCCESS)

    def test_first_error_extraction(self):
        """
        If the GetScalingGroupInfo effect fails, its exception is raised
        directly, without the FirstError wrapper.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        for srv in self.servers:
            srv.desired_lbs = pmap()

        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  get_all_convergence_data=gacd)

        # Perform the GetScalingGroupInfo by raising an exception
        dispatcher = ComposedDispatcher([
            EQFDispatcher([
                (GetScalingGroupInfo(
                    tenant_id='tenant-id',
                    group_id='group-id'),
                 lambda i: raise_(RuntimeError('foo')))]),
            self._get_dispatcher()])

        # And make sure that exception isn't wrapped in FirstError.
        e = self.assertRaises(RuntimeError, sync_perform, dispatcher, eff)
        self.assertEqual(str(e), 'foo')

    def test_deleting_group(self):
        """
        If group's status is DELETING, plan will be generated to delete
        all servers and group is deleted if the steps return SUCCESS. The
        group is not deleted is the step do not succeed
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)

        def _plan(dsg, *a):
            self.dsg = dsg
            return [TestStep(Effect(Constant((StepResult.SUCCESS, []))))]

        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  get_all_convergence_data=gacd, plan=_plan)

        # setup intents for DeleteGroup and GetScalingGroupInfo
        del_group = DeleteGroup(tenant_id=self.tenant_id,
                                group_id=self.group_id)
        self.manifest['status'] = 'DELETING'
        exp_intents = [(del_group, None),
                       (self.gsgi, (self.group, self.manifest))]

        disp = self._get_dispatcher(exp_intents)
        self.assertEqual(sync_perform(disp, eff), StepResult.SUCCESS)

        # desired capacity was changed to 0
        self.assertEqual(self.dsg.capacity, 0)

        # Group is not deleted if step result was not successful
        def fplan(*a):
            return [TestStep(Effect(Constant((StepResult.RETRY, []))))]

        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  get_all_convergence_data=gacd, plan=fplan)
        disp = self._get_dispatcher([(self.gsgi, (self.group, self.manifest))])
        # This succeeded without DeleteGroup performer being there ensuring
        # that it was not called
        self.assertEqual(sync_perform(disp, eff), StepResult.RETRY)

    def test_returns_retry(self):
        """
        If a step that results in RETRY is returned, and there are no FAILUREs,
        then the ultimate result of executing convergence will be a RETRY.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)

        def plan(*args, **kwargs):
            return pbag([
                TestStep(Effect(Constant((StepResult.SUCCESS, [])))),
                ConvergeLater(reasons=['mywish']),
                TestStep(Effect(Constant((StepResult.SUCCESS, []))))])

        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  plan=plan,
                                  get_all_convergence_data=gacd)
        dispatcher = self._get_dispatcher()
        self.assertEqual(sync_perform(dispatcher, eff), StepResult.RETRY)

    def test_returns_failure(self):
        """
        If a step that results in FAILURE is returned, then the ultimate result
        of executing convergence will be a FAILURE, regardless of the other
        step results.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)

        def plan(*args, **kwargs):
            return pbag([
                TestStep(Effect(Constant((StepResult.SUCCESS, [])))),
                ConvergeLater(reasons=['mywish']),
                TestStep(Effect(Constant((StepResult.SUCCESS, [])))),
                TestStep(Effect(Constant((StepResult.FAILURE, [])))),
                TestStep(Effect(Constant((StepResult.SUCCESS, [])))),
            ])

        eff = execute_convergence(self.tenant_id, self.group_id, log,
                                  plan=plan,
                                  get_all_convergence_data=gacd)
        dispatcher = self._get_dispatcher()
        self.assertEqual(sync_perform(dispatcher, eff), StepResult.FAILURE)


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
        desired_lbs = s(CLBDescription(lb_id='foo', port=80))
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
        desired_lbs = s(CLBDescription(lb_id='foo', port=1),
                        CLBDescription(lb_id='foo', port=2),
                        CLBDescription(lb_id='bar', port=3),
                        CLBDescription(lb_id='bar', port=4))
        servers = [
            server('id1', ServerState.ACTIVE, servicenet_address='1.1.1.1',
                   desired_lbs=desired_lbs),
            server('id2', ServerState.ACTIVE, servicenet_address='1.1.1.2',
                   desired_lbs=desired_lbs)
        ]
        self.assertEqual(determine_active(servers, lb_nodes), servers[:1])
