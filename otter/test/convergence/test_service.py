from effect import Constant, Effect, ParallelEffects, parallel
from effect.testing import Stub

import mock

from pyrsistent import freeze, pmap

from twisted.internet.defer import fail
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.model import (
    CLBDescription, NovaServer, ServerState)
from otter.convergence.service import (
    Converger, execute_convergence, server_to_json)
from otter.http import TenantScope, service_request
from otter.models.intents import ModifyGroupState
from otter.models.interface import GroupState
from otter.test.utils import (
    CheckFailure, LockMixin, mock_group, mock_log, resolve_effect,
    resolve_stubs)
from otter.util.fp import obj_assoc


class ConvergerTests(SynchronousTestCase):

    def setUp(self):
        clock = Clock()
        self.kz_client = mock.Mock(Lock=LockMixin().mock_lock())
        self.dispatcher = object()
        self.converger = Converger(clock, self.kz_client, self.dispatcher)
        self.state = GroupState('tenant-id', 'group-id', 'group-name',
                                {}, {}, None, {}, False)
        self.group = mock_group(self.state, 'tenant-id', 'group-id')
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}

    @mock.patch('time.time')
    def test_converge(self, time):
        """
        The ``converge`` method acquires a lock and performs the result of
        :func:`execute_convergence` within that lock.
        """
        perform = mock.Mock()

        def execute_convergence(group, desired, lc, now, log):
            return Effect(Constant((group, desired, lc, now, log)))

        log = mock_log()
        self.converger.start_convergence(
            log,
            self.group,
            self.state,
            self.lc,
            execute_convergence=execute_convergence,
            perform=perform)
        self.kz_client.Lock.assert_called_once_with(
            '/groups/group-id/converge_lock')
        # acquire is a monkey-patched partial function. :-(
        self.kz_client.Lock().acquire.func.assert_called_once_with(timeout=120)
        self.kz_client.Lock().release.assert_called_once_with()
        expected_converge_args = (self.group, 0, self.lc, time(), log)
        perform.assert_called_once_with(
            self.dispatcher,
            Effect(TenantScope(Effect(Constant(expected_converge_args)),
                               'tenant-id')))

    def test_converge_error_log(self):
        """If performance fails, the error is logged."""
        perform = mock.MagicMock()
        perform.return_value = fail(ZeroDivisionError('foo'))
        log = mock_log()
        self.converger.start_convergence(
            log,
            self.group, self.state, self.lc,
            execute_convergence=lambda *args: None,
            perform=perform)

        log.err.assert_called_once_with(
            CheckFailure(ZeroDivisionError),
            "Error when performing convergence",
            otter_msg_type='convergence-perform-error')


class ExecuteConvergenceTests(SynchronousTestCase):
    """Tests for :func:`execute_convergence`."""

    def setUp(self):
        self.state = GroupState('tenant-id', 'group-id', 'group-name',
                                {}, {}, None, {}, False)
        self.group = mock_group(self.state, 'tenant-id', 'group-id')
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

    def _get_gacd_func(self, group_id):
        def get_all_convergence_data(grp_id):
            self.assertEqual(grp_id, group_id)
            return Effect(Stub(Constant((self.servers, []))))
        return get_all_convergence_data

    def _assert_active(self, effect, active):
        self.assertIsInstance(effect.intent, ModifyGroupState)
        self.assertEqual(effect.intent.scaling_group, self.group)
        self.assertEqual(effect.intent.modifier(self.group, self.state),
                         obj_assoc(self.state, active=active))

    def test_no_steps(self):
        """
        If state of world matches desired, no steps are executed.
        """
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        for server in self.servers:
            server.desired_lbs = pmap()

        eff = execute_convergence(self.group, 2, self.lc, 0, log,
                                  get_all_convergence_data=gacd)
        mgs_eff = resolve_stubs(eff)
        expected_active = {'a': server_to_json(self.servers[0]),
                           'b': server_to_json(self.servers[1])}
        self._assert_active(mgs_eff, expected_active)
        p_effs = resolve_effect(mgs_eff, None)
        self.assertEqual(p_effs, parallel([]))

    def test_success(self):
        """
        Executes optimized steps if state of world does not match desired and
        returns the result of all the steps.
        """
        # The scenario: We have two servers but they're not in the LBs
        # yet. convergence should add them to the LBs.
        log = mock_log()
        gacd = self._get_gacd_func(self.group.uuid)
        eff = execute_convergence(self.group, 2, self.lc, 0, log,
                                  get_all_convergence_data=gacd)
        mgs_eff = resolve_stubs(eff)
        self._assert_active(mgs_eff, {})

        eff = resolve_effect(mgs_eff, None)
        # The steps are optimized
        self.assertIsInstance(eff.intent, ParallelEffects)
        self.assertEqual(len(eff.intent.effects), 1)
        expected_req = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            'loadbalancers/23/nodes',
            data=mock.ANY,
            success_pred=mock.ANY)
        got_req = eff.intent.effects[0].intent
        self.assertEqual(got_req, expected_req.intent)
        # separate check for nodes; they are unique, but can be in any order
        self.assertEqual(
            set(freeze(got_req.data['nodes'])),
            set([pmap({'weight': 1, 'type': 'PRIMARY', 'port': 80,
                       'condition': 'ENABLED', 'address': '10.0.0.2'}),
                 pmap({'weight': 1, 'type': 'PRIMARY', 'port': 80,
                       'condition': 'ENABLED', 'address': '10.0.0.1'})]))
        r = resolve_effect(eff, ['stuff'])
        # The result of the parallel is returned directly
        # TODO: This must change with issue #844.
        self.assertEqual(r, ['stuff'])
