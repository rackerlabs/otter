import mock

from pyrsistent import pmap

from twisted.internet.defer import fail
from twisted.internet.task import Clock
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.composition import get_desired_group_state
from otter.convergence.service import Converger
from otter.http import TenantScope
from otter.test.utils import CheckFailure, LockMixin, mock_log


class ConvergerTests(SynchronousTestCase):

    def setUp(self):
        clock = Clock()
        self.kz_client = mock.Mock(Lock=LockMixin().mock_lock())
        self.dispatcher = object()
        self.converger = Converger(clock, self.kz_client, self.dispatcher)
        self.lc = {'args': {'server': {'name': 'foo'}, 'loadBalancers': []}}

    def test_converge(self):
        """
        The ``converge`` method acquires a lock and performs the result of
        :func:`execute_convergence` within that lock.
        """
        perform = mock.Mock()
        exec_convergence_result = object()
        expected_desired_group_state = get_desired_group_state('group-id',
                                                               self.lc, 5)
        exec_calls = pmap().set(
            ('group-id', expected_desired_group_state), exec_convergence_result
        )
        self.converger.converge(
            mock_log(),
            'tenant-id',
            'group-id', 5, self.lc,
            perform=perform,
            execute_convergence=lambda gid, dgs: exec_calls.get((gid, dgs)))
        self.kz_client.Lock.assert_called_once_with(
            '/locks/convergence/group-id')
        self.kz_client.Lock().acquire.assert_called_once_with()
        self.kz_client.Lock().release.assert_called_once_with()
        perform.assert_called_once_with(
            self.dispatcher,
            TenantScope(exec_convergence_result, 'tenant-id'))

    def test_converge_error_log(self):
        """If performance fails, the error is logged."""
        perform = mock.MagicMock()
        perform.return_value = fail(ZeroDivisionError('foo'))
        log = mock_log()
        self.converger.converge(
            log,
            'tenant-id',
            'group-id', 5, self.lc,
            perform=perform)

        log.err.assert_called_once_with(CheckFailure(ZeroDivisionError))
