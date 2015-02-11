from effect import Constant, Effect

import mock

from pyrsistent import pmap

from twisted.internet.defer import fail
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.composition import get_desired_group_state
from otter.convergence.service import _converge_eff, Converger
from otter.http import TenantScope
from otter.models.interface import GroupState
from otter.test.utils import CheckFailure, LockMixin, mock_group, mock_log


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
        :func:`_converge_eff` within that lock.
        """
        perform = mock.Mock()

        def converge_eff(group, desired, lc, now, log):
            return Effect(Constant((group, desired, lc, now, log)))

        log = mock_log()
        self.converger.start_convergence(
            log,
            self.group,
            self.state,
            self.lc,
            converge_eff=converge_eff,
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
            converge_eff=lambda *args: None,
            perform=perform)

        log.err.assert_called_once_with(
            CheckFailure(ZeroDivisionError),
            "Error when performing convergence",
            otter_msg_type='convergence-perform-error')


# TODO: _converge_eff tests!
