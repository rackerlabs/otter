import sys
import time
import traceback
import uuid
from datetime import datetime

from effect import (
    ComposedDispatcher, Effect, Error, Func, base_dispatcher, sync_perform)
from effect.ref import (
    ModifyReference, ReadReference, Reference, reference_dispatcher)
from effect.testing import (
    SequenceDispatcher, parallel_sequence, perform_sequence)

from kazoo.exceptions import BadVersionError, NoNodeError
from kazoo.recipe.partitioner import PartitionState

import mock

from pyrsistent import freeze, pbag, pmap, pset, s, thaw

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import NoSuchCLBError, TenantScope
from otter.constants import CONVERGENCE_DIRTY_DIR
from otter.convergence.composition import get_desired_group_state
from otter.convergence.model import (
    CLBDescription, CLBNode, ConvergenceIterationStatus, ErrorReason,
    ServerState, StepResult)
from otter.convergence.service import (
    ConcurrentError,
    ConvergenceStarter,
    Converger,
    converge_all_groups,
    converge_one_group,
    execute_convergence, get_my_divergent_groups,
    is_autoscale_active,
    non_concurrently,
    trigger_convergence)
from otter.convergence.steps import CreateServer
from otter.log.intents import BoundFields, Log, LogErr, MsgWithTime
from otter.models.intents import (
    DeleteGroup,
    GetScalingGroupInfo,
    UpdateGroupErrorReasons,
    UpdateGroupStatus,
    UpdateServersCache)
from otter.models.interface import (
    GroupState, NoSuchScalingGroupError, ScalingGroupStatus)
from otter.test.convergence.test_planning import server
from otter.test.util.test_zk import ZNodeStatStub
from otter.test.utils import (
    CheckFailureValue, FakePartitioner,
    TestStep,
    intent_func,
    match_func,
    mock_group, mock_log,
    nested_sequence,
    noop,
    raise_,
    raise_to_exc_info,
    test_dispatcher,
    transform_eq)
from otter.util.zk import CreateOrSet, DeleteNode, GetChildren, GetStat


class TriggerConvergenceTests(SynchronousTestCase):
    """
    Tests for :func:`trigger_convergence`
    """

    def test_success(self):
        """
        Divergent flag is set with bound log and msg is logged
        """
        seq = [
            (CreateOrSet(path="/groups/divergent/t_g", content="dirty"), noop),
            (Log("mark-dirty-success", {}), noop)
        ]
        self.assertEqual(
            perform_sequence(seq, trigger_convergence("t", "g")),
            None)

    def test_failure(self):
        """
        If setting divergent flag errors, then error is logged and raised
        """
        seq = [
            (CreateOrSet(path="/groups/divergent/t_g", content="dirty"),
             lambda i: raise_(ValueError("oops"))),
            (LogErr(CheckFailureValue(ValueError("oops")),
                    "mark-dirty-failure", {}),
             noop)
        ]
        self.assertRaises(
            ValueError, perform_sequence, seq, trigger_convergence("t", "g"))


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
            'mark-dirty-success', tenant_id='tenant', scaling_group_id='group')

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
            'mark-dirty-failure', tenant_id='tenant', scaling_group_id='group')


class ConvergerTests(SynchronousTestCase):
    """Tests for :obj:`Converger`."""

    def setUp(self):
        self.log = mock_log()
        self.num_buckets = 10

    def _converger(self, converge_all_groups, dispatcher=None):
        if dispatcher is None:
            dispatcher = _get_dispatcher()
        return Converger(
            self.log, dispatcher, self.num_buckets,
            self._pfactory, build_timeout=3600,
            interval=15,
            converge_all_groups=converge_all_groups)

    def _pfactory(self, buckets, log, got_buckets):
        self.assertEqual(buckets, range(self.num_buckets))
        self.fake_partitioner = FakePartitioner(log, got_buckets)
        return self.fake_partitioner

    def _log_sequence(self, intents):
        uid = uuid.uuid4()
        exp_uid = str(uid)
        return SequenceDispatcher([
            (Func(uuid.uuid4), lambda i: uid),
            (BoundFields(effect=mock.ANY,
                         fields={'otter_service': 'converger',
                                 'converger_run_id': exp_uid}),
             nested_sequence(intents)),
        ])

    def test_buckets_acquired(self):
        """
        When buckets are allocated, the result of converge_all_groups is
        performed.
        """
        def converge_all_groups(currently_converging, recent, _my_buckets,
                                all_buckets, divergent_flags, build_timeout,
                                interval):
            return Effect(
                ('converge-all', currently_converging, _my_buckets,
                 all_buckets, divergent_flags, build_timeout, interval))

        my_buckets = [0, 5]
        bound_sequence = [
            (GetChildren(CONVERGENCE_DIRTY_DIR),
                lambda i: ['flag1', 'flag2']),
            (('converge-all',
                transform_eq(lambda cc: cc is converger.currently_converging,
                             True),
                my_buckets,
                range(self.num_buckets),
                ['flag1', 'flag2'],
                3600,
                15),
                lambda i: 'foo')
        ]
        sequence = self._log_sequence(bound_sequence)

        converger = self._converger(converge_all_groups, dispatcher=sequence)

        with sequence.consume():
            result, = self.fake_partitioner.got_buckets(my_buckets)
        self.assertEqual(self.successResultOf(result), 'foo')

    def test_buckets_acquired_errors(self):
        """
        Errors raised from performing the converge_all_groups effect are
        logged, and None is the ultimate result.
        """
        def converge_all_groups(currently_converging, recent, _my_buckets,
                                all_buckets, divergent_flags, build_timeout,
                                interval):
            return Effect('converge-all')

        bound_sequence = [
            (GetChildren(CONVERGENCE_DIRTY_DIR),
                lambda i: ['flag1', 'flag2']),
            ('converge-all', lambda i: raise_(RuntimeError('foo'))),
            (LogErr(
                CheckFailureValue(RuntimeError('foo')),
                'converge-all-groups-error', {}), noop)
        ]
        sequence = self._log_sequence(bound_sequence)

        # relying on the side-effect of setting up self.fake_partitioner
        self._converger(converge_all_groups, dispatcher=sequence)

        with sequence.consume():
            result, = self.fake_partitioner.got_buckets([0])
        self.assertEqual(self.successResultOf(result), None)

    def test_divergent_changed_not_acquired(self):
        """
        When notified that divergent groups have changed and we have not
        acquired our buckets, nothing is done.
        """
        dispatcher = SequenceDispatcher([])  # "nothing happens"
        converger = self._converger(lambda *a, **kw: 1 / 0,
                                    dispatcher=dispatcher)
        # Doesn't try to get buckets
        self.fake_partitioner.get_current_buckets = lambda s: 1 / 0
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
        def converge_all_groups(currently_converging, recent, _my_buckets,
                                all_buckets, divergent_flags, build_timeout,
                                interval):
            return Effect(('converge-all-groups', divergent_flags))

        intents = [
            (('converge-all-groups', ['group1', 'group2']),
             noop)
        ]
        sequence = self._log_sequence(intents)

        converger = self._converger(converge_all_groups, dispatcher=sequence)

        # sha1('group1') % 10 == 3
        self.fake_partitioner.current_state = PartitionState.ACQUIRED
        self.fake_partitioner.my_buckets = [3]
        with sequence.consume():
            converger.divergent_changed(['group1', 'group2'])


def add_to_recently(recently, group_id, cvg_time):
    return (ModifyReference(recently,
                            match_func(pmap(), pmap({group_id: cvg_time}))),
            noop)


def add_to_currently(currently, group_id):
    return (ModifyReference(currently,
                            match_func(pset(), pset([group_id]))),
            noop)


class ConvergeOneGroupTests(SynchronousTestCase):
    """Tests for :func:`converge_one_group`."""

    def setUp(self):
        self.tenant_id = 'tenant-id'
        self.group_id = 'g1'
        self.version = 5

    def _execute_convergence(self, tenant_id, group_id, build_timeout):
        return Effect(('ec', tenant_id, group_id, build_timeout))

    def _verify_sequence(self, sequence, converging=Reference(pset()),
                         recent=Reference(pmap()), allow_refs=True):
        """
        Verify that sequence is executed
        """
        eff = converge_one_group(
            converging, recent, self.tenant_id, self.group_id, self.version,
            3600, execute_convergence=self._execute_convergence)
        fb_dispatcher = _get_dispatcher() if allow_refs else base_dispatcher
        perform_sequence(sequence, eff, fallback_dispatcher=fb_dispatcher)

    def test_success(self):
        """When execute_convergence returns Stop, the dirty flag is deleted."""
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Stop()),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version), noop),
            (Log('mark-clean-success', {}), noop)
        ]
        self._verify_sequence(sequence)

    def test_record_recently_converged(self):
        """
        After converging, the group is added to ``recently_converged`` -- but
        *before* being removed from ``currently_converging``, to avoid race
        conditions.
        """
        currently = Reference(pset())
        recently = Reference(pmap())
        remove_from_currently = match_func(pset([self.group_id]), pset([]))
        sequence = [
            (ReadReference(currently), lambda i: pset()),
            add_to_currently(currently, self.group_id),
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Stop()),
            (Func(time.time), lambda i: 100),
            add_to_recently(recently, self.group_id, 100),
            (ModifyReference(currently, remove_from_currently), noop),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version), noop),
            (Log('mark-clean-success', {}), noop)
        ]
        eff = converge_one_group(
            currently, recently, self.tenant_id, self.group_id, self.version,
            3600, execute_convergence=self._execute_convergence)
        perform_sequence(sequence, eff)

    def test_non_concurrent(self):
        """
        Won't run execute_convergence if it's already running for the same
        group ID.
        """
        self._verify_sequence([], Reference(pset([self.group_id])))

    def test_no_scaling_group(self):
        """
        When the scaling group disappears, a fatal error is logged and the
        dirty flag is cleaned up.
        """
        expected_error = NoSuchScalingGroupError(self.tenant_id, self.group_id)
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: raise_(expected_error)),
            (LogErr(CheckFailureValue(expected_error),
                    'converge-fatal-error', {}),
             noop),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version), noop),
            (Log('mark-clean-success', {}), noop)
        ]
        self._verify_sequence(sequence)

    def test_unexpected_errors(self):
        """
        Unexpected exceptions log a non-fatal error and don't clean up the
        dirty flag.
        """
        converging = Reference(pset())
        recent = Reference(pmap())
        expected_error = RuntimeError('oh no!')
        sequence = [
            (ReadReference(converging), lambda i: pset()),
            add_to_currently(converging, self.group_id),
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: raise_(expected_error)),
            (Func(time.time), lambda i: 100),
            add_to_recently(recent, self.group_id, 100),
            (ModifyReference(converging,
                             match_func(pset([self.group_id]), pset())),
             noop),
            (LogErr(CheckFailureValue(expected_error),
                    'converge-non-fatal-error', {}),
             noop),
        ]
        self._verify_sequence(sequence, converging=converging, recent=recent,
                              allow_refs=False)

    def test_delete_node_version_mismatch(self):
        """
        When the version of the dirty flag changes during a call to
        converge_one_group, and DeleteNode raises a BadVersionError, the error
        is logged and nothing else is cleaned up.
        """
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Stop()),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version),
             lambda i: raise_(BadVersionError())),
            (Log('mark-clean-skipped',
                 dict(path='/groups/divergent/tenant-id_g1',
                      dirty_version=self.version)), noop)
        ]
        self._verify_sequence(sequence)

    def test_delete_node_not_found(self):
        """
        When DeleteNode raises a NoNodeError, a message is logged and nothing
        else is cleaned up.
        """
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Stop()),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version),
             lambda i: raise_(NoNodeError())),
            (Log('mark-clean-not-found',
                 dict(path='/groups/divergent/tenant-id_g1',
                      dirty_version=self.version)), noop)
        ]
        self._verify_sequence(sequence)

    def test_delete_node_other_error(self):
        """When marking clean raises arbitrary errors, an error is logged."""
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Stop()),
            (DeleteNode(path='/groups/divergent/tenant-id_g1',
                        version=self.version),
             lambda i: raise_(ZeroDivisionError())),
            (LogErr(CheckFailureValue(ZeroDivisionError()),
                    'mark-clean-failure',
                    dict(path='/groups/divergent/tenant-id_g1',
                         dirty_version=self.version)), noop)
        ]
        self._verify_sequence(sequence)

    def test_retry(self):
        """
        When execute_convergence returns Continue, the divergent flag is not
        deleted.
        """
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.Continue())
        ]
        self._verify_sequence(sequence)

    def test_delete_flag_unconditionally_when_group_deleted(self):
        """
        When execute_convergence's return value indicates the group has been
        deleted, the divergent flag is unconditionally deleted (ignoring
        mismatched versions), because a re-converge would be fruitless.
        """
        sequence = [
            (('ec', self.tenant_id, self.group_id, 3600),
             lambda i: ConvergenceIterationStatus.GroupDeleted()),
            (DeleteNode(path='/groups/divergent/tenant-id_g1', version=-1),
             noop),
            (Log('mark-clean-success', {}), noop),
        ]
        self._verify_sequence(sequence)


class ConvergeAllGroupsTests(SynchronousTestCase):
    """Tests for :func:`converge_all_groups`."""

    def setUp(self):
        self.currently_converging = Reference(pset())
        self.recently_converged = Reference(pmap())
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
            self.currently_converging, self.recently_converged,
            self.my_buckets, self.all_buckets,
            flags,
            3600,
            15,
            converge_one_group=self._converge_one_group)

    def _converge_one_group(self, currently_converging, recently_converged,
                            tenant_id, group_id, version, build_timeout):
        return Effect(
            ('converge', tenant_id, group_id, version, build_timeout))

    def _expect_group_converged(self, tenant_id, group_id):
        """
        Return a SequenceDispatcher two-tuple that matches the usual sequence
        of intents for converging a single group.
        """
        return (
            BoundFields(mock.ANY,
                        dict(tenant_id=tenant_id, scaling_group_id=group_id)),
            nested_sequence([
                (GetStat(
                    path='/groups/divergent/{tenant_id}_{group_id}'.format(
                        tenant_id=tenant_id, group_id=group_id)),
                 lambda i: ZNodeStatStub(version=5)),
                (TenantScope(mock.ANY, tenant_id),
                 nested_sequence([
                     (('converge', tenant_id, group_id, 5, 3600),
                      lambda i: 'converged {}!'.format(group_id)),
                 ])),
            ]))

    def test_converge_all_groups(self):
        """
        Fetches divergent groups and runs converge_one_group for each one
        needing convergence.
        """
        eff = self._converge_all_groups(['00_g1', '01_g2'])
        sequence = [
            (ReadReference(ref=self.currently_converging),
             lambda i: pset()),
            (Log('converge-all-groups',
                 dict(group_infos=self.group_infos, currently_converging=[])),
             noop),
            (ReadReference(self.recently_converged), lambda i: pmap()),
            (Func(time.time), lambda i: 100),
            parallel_sequence([[self._expect_group_converged('00', 'g1')],
                               [self._expect_group_converged('01', 'g2')]])
        ]
        self.assertEqual(perform_sequence(sequence, eff),
                         ['converged g1!', 'converged g2!'])

    def test_filter_out_currently_converging(self):
        """
        If a group is already being converged, its dirty flag is not statted
        and convergence is not run for it.
        """
        eff = self._converge_all_groups(['00_g1', '01_g2'])
        sequence = [
            (ReadReference(ref=self.currently_converging),
             lambda i: pset(['g1'])),
            (Log('converge-all-groups',
                 dict(group_infos=[self.group_infos[1]],
                      currently_converging=['g1'])),
             noop),
            (ReadReference(ref=self.recently_converged), lambda i: pmap()),
            (Func(time.time), lambda i: 100),
            parallel_sequence([[self._expect_group_converged('01', 'g2')]])
        ]
        self.assertEqual(perform_sequence(sequence, eff), ['converged g2!'])

    def test_filter_out_recently_converged(self):
        """
        If a group was recently converged, it will not be converged again.
        """
        eff = self._converge_all_groups(['00_g1'])
        sequence = [
            (ReadReference(ref=self.currently_converging), lambda i: pset([])),
            (Log('converge-all-groups',
                 dict(group_infos=[self.group_infos[0]],
                      currently_converging=[])),
             noop),
            (ReadReference(ref=self.recently_converged),
             lambda i: pmap({'g1': 5})),
            (Func(time.time), lambda i: 14),
            parallel_sequence([])  # No groups to converge
        ]
        self.assertEqual(perform_sequence(sequence, eff), [])

    def test_dont_filter_out_non_recently_converged(self):
        """
        If a group was converged in the past but not recently, it will be
        cleaned from the ``recently_converged`` map, and it will be converged.
        """
        # g1: converged a while ago; divergent -> removed and converged
        # g2: converged recently; not divergent -> not converged
        # g3: converged a while ago; not divergent -> removed and not converged
        eff = self._converge_all_groups(['00_g1'])
        sequence = [
            (ReadReference(ref=self.currently_converging), lambda i: pset([])),
            (Log('converge-all-groups',
                 dict(group_infos=[self.group_infos[0]],
                      currently_converging=[])),
             noop),
            (ReadReference(ref=self.recently_converged),
             lambda i: pmap({'g1': 4, 'g2': 10, 'g3': 0})),
            (Func(time.time), lambda i: 20),
            (ModifyReference(self.recently_converged,
                             match_func("literally anything",
                                        pmap({'g2': 10}))),
             noop),
            parallel_sequence([[self._expect_group_converged('00', 'g1')]])
        ]
        self.assertEqual(perform_sequence(sequence, eff), ['converged g1!'])

    def test_no_log_on_no_groups(self):
        """When there's no work, no log message is emitted."""
        def converge_one_group(*args, **kwargs):
            1 / 0  # This should not be run

        result = converge_all_groups(
            self.currently_converging, self.recently_converged,
            self.my_buckets, self.all_buckets, [],
            3600, 15, converge_one_group=converge_one_group)
        self.assertEqual(sync_perform(_get_dispatcher(), result), None)

    def test_ignore_disappearing_divergent_flag(self):
        """
        When the divergent flag disappears just as we're starting to converge,
        the group does not get converged and None is returned as its result.

        This happens when a concurrent convergence iteration is just finishing
        up.
        """
        eff = self._converge_all_groups(['00_g1'])

        def get_bound_sequence(tid, gid):
            # since this GetStat is going to return None, no more effects will
            # be run. This is the crux of what we're testing.
            znode = '/groups/divergent/{}_{}'.format(tid, gid)
            return [
                (GetStat(path=znode), noop),
                (Log('converge-divergent-flag-disappeared',
                     fields={'znode': znode}),
                 noop)]

        sequence = [
            (ReadReference(ref=self.currently_converging), lambda i: pset()),
            (Log('converge-all-groups',
                 dict(group_infos=[self.group_infos[0]],
                      currently_converging=[])),
             noop),
            (ReadReference(ref=self.recently_converged), lambda i: pmap()),
            (Func(time.time), lambda i: 100),
            parallel_sequence([
                [(BoundFields(mock.ANY, fields={'tenant_id': '00',
                                                'scaling_group_id': 'g1'}),
                  nested_sequence(get_bound_sequence('00', 'g1')))],
             ]),
        ]
        self.assertEqual(perform_sequence(sequence, eff), [None])


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
                                {}, {}, None, {}, False,
                                ScalingGroupStatus.ACTIVE, desired=2)
        self.group = mock_group(self.state, self.tenant_id, self.group_id)
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}
        self.desired_lbs = s(CLBDescription(lb_id='23', port=80))
        self.servers = (
            server('a', ServerState.ACTIVE, servicenet_address='10.0.0.1',
                   desired_lbs=self.desired_lbs,
                   links=freeze([{'href': 'link1', 'rel': 'self'}])),
            server('b', ServerState.ACTIVE, servicenet_address='10.0.0.2',
                   desired_lbs=self.desired_lbs,
                   links=freeze([{'href': 'link2', 'rel': 'self'}]))
        )
        self.state_active = {}
        self.cache = [thaw(self.servers[0].json), thaw(self.servers[1].json)]
        self.gsgi = GetScalingGroupInfo(tenant_id='tenant-id',
                                        group_id='group-id')
        self.manifest = {  # Many details elided!
            'state': self.state,
            'launchConfiguration': self.lc,
        }
        self.gsgi_result = (self.group, self.manifest)
        self.now = datetime(1970, 1, 1)

    def get_seq(self, with_cache=True):
        exec_seq = [
            parallel_sequence([
                [(self.gsgi, lambda i: self.gsgi_result)],
                [(("gacd", self.tenant_id, self.group_id, self.now),
                 lambda i: (self.servers, ()))]
            ])
        ]
        if with_cache:
            exec_seq.append(
                (UpdateServersCache(
                    self.tenant_id, self.group_id, self.now, self.cache),
                 noop)
            )
        return [
            (Log("begin-convergence", {}), noop),
            (Func(datetime.utcnow), lambda i: self.now),
            (MsgWithTime("gather-convergence-data", mock.ANY),
             nested_sequence(exec_seq))
        ]

    def _invoke(self, plan=None):
        kwargs = {'plan': plan} if plan is not None else {}
        return execute_convergence(
            self.tenant_id, self.group_id, build_timeout=3600,
            get_all_convergence_data=intent_func("gacd"), **kwargs)

    def test_no_steps(self):
        """
        If state of world matches desired, no steps are executed, but the
        `active` servers are still updated, and SUCCESS is the return value.
        """
        for serv in self.servers:
            serv.desired_lbs = pset()
        sequence = [
            parallel_sequence([]),
            (Log('execute-convergence', mock.ANY), noop),
            (Log('execute-convergence-results',
                 {'results': [], 'worst_status': 'SUCCESS'}), noop),
            (UpdateServersCache(
                "tenant-id", "group-id", self.now,
                [thaw(self.servers[0].json.set('_is_as_active', True)),
                 thaw(self.servers[1].json.set("_is_as_active", True))]),
             noop)
        ]
        self.state_active = {
            'a': {'id': 'a', 'links': [{'href': 'link1', 'rel': 'self'}]},
            'b': {'id': 'b', 'links': [{'href': 'link2', 'rel': 'self'}]}
        }
        self.cache[0]["_is_as_active"] = True
        self.cache[1]["_is_as_active"] = True
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke()),
            ConvergenceIterationStatus.Stop())

    def test_success(self):
        """
        Executes the plan and returns SUCCESS when that's the most severe
        result.
        """
        dgs = get_desired_group_state(self.group_id, self.lc, 2)
        deleted = server(
            'c', ServerState.DELETED, servicenet_address='10.0.0.3',
            desired_lbs=self.desired_lbs,
            links=freeze([{'href': 'link3', 'rel': 'self'}]))
        self.servers += (deleted,)

        steps = [
            TestStep(
                Effect(
                    {'dgs': dgs,
                     'servers': self.servers,
                     'lb_nodes': (),
                     'now': 0})
                .on(lambda _: (StepResult.SUCCESS, [])))]

        def plan(dgs, servers, lb_nodes, now, build_timeout):
            self.assertEqual(build_timeout, 3600)
            return steps

        sequence = [
            parallel_sequence([]),
            (Log('execute-convergence',
                 dict(servers=self.servers, lb_nodes=(), steps=steps,
                      now=self.now, desired=dgs)), noop),
            parallel_sequence([
                [({'dgs': dgs, 'servers': self.servers,
                   'lb_nodes': (), 'now': 0},
                  noop)]
            ]),
            (Log('execute-convergence-results',
                 {'results': [{'step': steps[0],
                               'result': StepResult.SUCCESS,
                               'reasons': []}],
                  'worst_status': 'SUCCESS'}), noop),
            # Note that servers arg is non-deleted servers
            (UpdateServersCache(
                "tenant-id", "group-id", self.now,
                [thaw(self.servers[0].json.set("_is_as_active", True)),
                 thaw(self.servers[1].json.set("_is_as_active", True))]),
             noop)
        ]

        # all the servers updated in cache in beginning
        self.cache.append(thaw(deleted.json))

        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Stop())

    def test_first_error_extraction(self):
        """
        If the GetScalingGroupInfo effect fails, its exception is raised
        directly, without the FirstError wrapper.
        """
        # Perform the GetScalingGroupInfo by raising an exception
        sequence = [
            (Log("begin-convergence", {}), noop),
            (Func(datetime.utcnow), lambda i: self.now),
            (MsgWithTime("gather-convergence-data", mock.ANY),
             nested_sequence([
                parallel_sequence([
                    [(self.gsgi, lambda i: raise_(RuntimeError('foo')))],
                    [("anything", noop)]
                ])
             ]))
        ]

        # And make sure that exception isn't wrapped in FirstError.
        e = self.assertRaises(
            RuntimeError, perform_sequence, sequence, self._invoke(),
            test_dispatcher())
        self.assertEqual(str(e), 'foo')

    def test_log_reasons(self):
        """When a step doesn't succeed, useful information is logged."""
        try:
            1 / 0
        except ZeroDivisionError:
            exc_info = sys.exc_info()

        step = TestStep(Effect("step_intent"))

        def plan(*args, **kwargs):
            return pbag([step])

        exc_msg = "ZeroDivisionError('integer division or modulo by zero',)"
        tb_msg = ''.join(traceback.format_exception(*exc_info))
        expected_fields = {
            'results': [
                {
                    'step': step,
                    'result': StepResult.RETRY,
                    'reasons': [
                        {'exception': exc_msg, 'traceback': tb_msg},
                        {'string': 'foo'},
                        {'foo': 'bar'}
                    ]
                }
            ],
            'worst_status': 'RETRY'}
        sequence = [
            parallel_sequence([]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            parallel_sequence([
                [("step_intent", lambda i: (
                     StepResult.RETRY, [
                         ErrorReason.Exception(exc_info),
                         ErrorReason.String('foo'),
                         ErrorReason.Structured({'foo': 'bar'})]))]
            ]),
            (Log(msg='execute-convergence-results', fields=expected_fields),
             noop)
        ]

        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Continue())

    def test_log_steps(self):
        """The steps to be executed are logged to cloud feeds."""
        step = CreateServer(server_config=pmap({"foo": "bar"}))
        step.as_effect = lambda: Effect("create-server")

        def plan(*args, **kwargs):
            return pbag([step])

        sequence = [
            parallel_sequence([
                [parallel_sequence([
                    [(Log('convergence-create-servers',
                          {'num_servers': 1, 'server_config': {'foo': 'bar'},
                           'cloud_feed': True}),
                      noop)]
                ])]
            ]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            parallel_sequence([
                [("create-server", lambda i: (StepResult.RETRY, []))]
            ]),
            (Log(msg='execute-convergence-results', fields=mock.ANY), noop)
        ]

        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Continue())

    def _test_deleting_group(self, step_result, with_delete, exec_result):

        def _plan(dsg, *a, **kwargs):
            self.dsg = dsg
            return [TestStep(Effect("step"))]

        self.state.status = ScalingGroupStatus.DELETING
        sequence = [
            parallel_sequence([]),
            (Log('execute-convergence', mock.ANY), noop),
            parallel_sequence([
                [("step", lambda i: (step_result, []))]
            ]),
            (Log('execute-convergence-results', mock.ANY), noop),
        ]
        if with_delete:
            sequence.append((DeleteGroup(tenant_id=self.tenant_id,
                                         group_id=self.group_id), noop))
        self.assertEqual(
            # skipping cache update intents returned in get_seq()
            perform_sequence(self.get_seq(False) + sequence,
                             self._invoke(_plan)),
            exec_result)
        # desired capacity was changed to 0
        self.assertEqual(self.dsg.capacity, 0)

    def test_deleting_group(self):
        """
        If group's status is DELETING, plan will be generated to delete
        all servers and group is deleted if the steps return SUCCESS
        """
        self._test_deleting_group(StepResult.SUCCESS, True,
                                  ConvergenceIterationStatus.GroupDeleted())

    def test_deleting_group_retry(self):
        """
        If group's status is DELETING, plan will be generated to delete
        all servers and group is not deleted if the steps return RETRY
        """
        self._test_deleting_group(StepResult.RETRY, False,
                                  ConvergenceIterationStatus.Continue())

    def test_returns_retry(self):
        """
        If a step that results in RETRY is returned, and there are no FAILUREs,
        then the ultimate result of executing convergence will be a Continue.
        """
        def plan(*args, **kwargs):
            return [
                TestStep(Effect("step1")),
                TestStep(Effect("retry"))]

        sequence = [
            parallel_sequence([]),
            (Log('execute-convergence', mock.ANY), noop),
            parallel_sequence([
                [("step1", lambda i: (StepResult.SUCCESS, []))],
                [("retry", lambda i: (StepResult.RETRY,
                                      [ErrorReason.String('mywish')]))],
            ]),
            (Log('execute-convergence-results', mock.ANY), noop)
        ]
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Continue())

    def test_returns_failure_set_error_state(self):
        """
        The group is put into ERROR state if any step returns FAILURE, and
        Stop is the final result of convergence.
        """
        exc_info = raise_to_exc_info(NoSuchCLBError(lb_id=u'nolb1'))
        exc_info2 = raise_to_exc_info(NoSuchCLBError(lb_id=u'nolb2'))

        def plan(*args, **kwargs):
            return [
                TestStep(Effect("success1")),
                TestStep(Effect("retry")),
                TestStep(Effect("success2")),
                TestStep(Effect("fail1")),
                TestStep(Effect("fail2")),
                TestStep(Effect("success3"))]

        def success(i):
            return StepResult.SUCCESS, []

        sequence = [
            parallel_sequence([]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            parallel_sequence([
                [("success1", success)],
                [("retry", lambda i: (StepResult.RETRY, []))],
                [("success2", success)],
                [("fail1", lambda i: (StepResult.FAILURE,
                                      [ErrorReason.Exception(exc_info)]))],
                [("fail2", lambda i: (StepResult.FAILURE,
                                      [ErrorReason.Exception(exc_info2)]))],
                [("success3", success)],
            ]),
            (Log(msg='execute-convergence-results', fields=mock.ANY), noop),
            (UpdateGroupStatus(scaling_group=self.group,
                               status=ScalingGroupStatus.ERROR),
             noop),
            (Log('group-status-error',
                 dict(isError=True, cloud_feed=True, status='ERROR',
                      reasons=['Cloud Load Balancer does not exist: nolb1',
                               'Cloud Load Balancer does not exist: nolb2'])),
             noop),
            (UpdateGroupErrorReasons(
                self.group,
                ['Cloud Load Balancer does not exist: nolb1',
                 'Cloud Load Balancer does not exist: nolb2']), noop)
        ]
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Stop())

    def test_failure_unknown_reasons(self):
        """
        The group is put into ERROR state if any step returns FAILURE, and
        unknown error is defaulted to fixed reason
        """
        exc_info = raise_to_exc_info(ValueError('wat'))

        def plan(*args, **kwargs):
            return [TestStep(Effect("fail"))]

        sequence = [
            parallel_sequence([]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            parallel_sequence([
                [("fail", lambda i: (StepResult.FAILURE,
                                     [ErrorReason.Exception(exc_info)]))]
            ]),
            (Log(msg='execute-convergence-results', fields=mock.ANY), noop),
            (UpdateGroupStatus(scaling_group=self.group,
                               status=ScalingGroupStatus.ERROR),
             noop),
            (Log('group-status-error',
                 dict(isError=True, cloud_feed=True, status='ERROR',
                      reasons=['Unknown error occurred'])),
             noop),
            (UpdateGroupErrorReasons(self.group, ['Unknown error occurred']),
             noop)
        ]
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Stop())

    def test_reactivate_group_on_success_after_steps(self):
        """
        When the group started in ERROR state, and convergence succeeds, the
        group is put back into ACTIVE.
        """
        self.manifest['state'].status = ScalingGroupStatus.ERROR

        def plan(*args, **kwargs):
            return pbag([TestStep(Effect("step"))])

        sequence = [
            parallel_sequence([]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            parallel_sequence([
                [("step", lambda i: (StepResult.SUCCESS, []))]
            ]),
            (Log(msg='execute-convergence-results', fields=mock.ANY), noop),
            (UpdateGroupStatus(scaling_group=self.group,
                               status=ScalingGroupStatus.ACTIVE),
             noop),
            (Log('group-status-active',
                 dict(cloud_feed=True, status='ACTIVE')),
             noop),
            (UpdateServersCache(
                "tenant-id", "group-id", self.now,
                [thaw(self.servers[0].json.set('_is_as_active', True)),
                 thaw(self.servers[1].json.set('_is_as_active', True))]),
             noop),
        ]
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke(plan)),
            ConvergenceIterationStatus.Stop())

    def test_reactivate_group_on_success_with_no_steps(self):
        """
        When the group started in ERROR state, and convergence succeeds, the
        group is put back into ACTIVE, even if there were no steps to execute.
        """
        self.manifest['state'].status = ScalingGroupStatus.ERROR
        for serv in self.servers:
            serv.desired_lbs = pset()
        sequence = [
            parallel_sequence([]),
            (Log(msg='execute-convergence', fields=mock.ANY), noop),
            (Log(msg='execute-convergence-results', fields=mock.ANY), noop),
            (UpdateGroupStatus(scaling_group=self.group,
                               status=ScalingGroupStatus.ACTIVE),
             noop),
            (Log('group-status-active',
                 dict(cloud_feed=True, status='ACTIVE')),
             noop),
            (UpdateServersCache(
                "tenant-id", "group-id", self.now,
                [thaw(self.servers[0].json.set("_is_as_active", True)),
                 thaw(self.servers[1].json.set("_is_as_active", True))]),
             noop)
        ]
        self.state_active = {
            'a': {'id': 'a', 'links': [{'href': 'link1', 'rel': 'self'}]},
            'b': {'id': 'b', 'links': [{'href': 'link2', 'rel': 'self'}]}
        }
        self.cache[0]["_is_as_active"] = True
        self.cache[1]["_is_as_active"] = True
        self.assertEqual(
            perform_sequence(self.get_seq() + sequence, self._invoke()),
            ConvergenceIterationStatus.Stop())


class IsAutoscaleActiveTests(SynchronousTestCase):
    """Tests for :func:`is_autoscale_active`."""

    def test_active(self):
        """Built server with no desired LBs is active."""
        self.assertEqual(
            is_autoscale_active(server('id1', ServerState.ACTIVE), []),
            True)

    def test_non_active(self):
        """ Non-active server is not considered AS active """
        self.assertEqual(
            is_autoscale_active(server('id1', ServerState.BUILD), []),
            False)

    def test_lb_pending(self):
        """
        When a server should be in a LB but it's not, it's not active.
        """
        desired_lbs = s(CLBDescription(lb_id='foo', port=80))
        lb_nodes = [
            CLBNode(node_id='x',
                    description=CLBDescription(lb_id='foo', port=80),
                    address='1.1.1.3')]
        self.assertEqual(
            is_autoscale_active(
                server('id1', ServerState.ACTIVE, servicenet_address='1.1.1.1',
                       desired_lbs=desired_lbs),
                lb_nodes),
            False)

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
        self.assertEqual(
            is_autoscale_active(
                server('id1', ServerState.ACTIVE, servicenet_address='1.1.1.1',
                       desired_lbs=desired_lbs),
                lb_nodes),
            True)
