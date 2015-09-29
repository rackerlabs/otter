"""
Tests for the utility functions for convergence black-box testing.
"""
from pyrsistent import pmap, pset

from twisted.internet.defer import FirstError, fail
from twisted.internet.error import ConnectionRefusedError
from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.model import (
    DesiredServerGroupState,
    NovaServer,
    ServerState
)

from otter.integration.lib.utils import (
    GroupState,
    OvershootError,
    UndershootError,
    diagnose,
    measure_progress
)

from otter.util.http import APIError, UpstreamError


class MeasureProgressTests(SynchronousTestCase):
    """
    Tests for :func:`measure_progress`.
    """
    def _create_servers(self, n, state=ServerState.ACTIVE):
        """
        Create some dummy test servers.
        """
        return pset([
            NovaServer(id=str(i), state=state, created=123456789.,
                       image_id='image', flavor_id='flavor')
            for i in xrange(n)
        ])

    def test_capacity_closer_to_desired_when_scaling_up(self):
        """
        If the capacity moves closer to the desired, progress has been
        made.
        """
        previous_state = GroupState(
            servers=self._create_servers(2),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=self._create_servers(4),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 2)

    def test_capacity_closer_to_desired_when_scaling_down(self):
        """
        If the capacity moves closer to the desired, progress has been
        made.
        """
        previous_state = GroupState(
            servers=self._create_servers(4),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=self._create_servers(2),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=1,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 2)

    def test_overshoot(self):
        """
        When overshooting the desired capacity (group was below desired,
        and is now above desired), no progress was made.
        """
        previous_state = GroupState(
            servers=self._create_servers(4),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=self._create_servers(6),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        self.assertRaises(
            OvershootError,
            measure_progress, previous_state, current_state, desired_state)

    def test_undershoot(self):
        """
        When undershooting the desired capacity (group was above desired,
        and is now below desired), no progress was made.
        """
        previous_state = GroupState(
            servers=self._create_servers(6),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=self._create_servers(4),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        self.assertRaises(
            UndershootError,
            measure_progress, previous_state, current_state, desired_state)

    def test_building_servers_towards_desired_capacity(self):
        """
        When some servers are being built, which would put us closer to
        the desired capacity, progress is being made.
        """
        previous_state = GroupState(
            servers=self._create_servers(2),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=(self._create_servers(2, state=ServerState.ACTIVE) |
                     self._create_servers(2, state=ServerState.BUILD)),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 2)

    def test_servers_going_from_build_to_error(self):
        """
        When some servers go from build to error, no progress was made.
        """
        previous_state = GroupState(
            servers=self._create_servers(3, state=ServerState.BUILD),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE) |
                     self._create_servers(2, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 0)

    def test_servers_going_from_build_to_error_with_reaping(self):
        """
        When some servers go from build to error, no progress was
        made. That works correctly even if some of the errored
        machines get reaped in the mean while.
        """
        previous_state = GroupState(
            servers=self._create_servers(3, state=ServerState.BUILD),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE) |
                     self._create_servers(1, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 0)

    def test_reaping_errored_servers(self):
        """
        Errored servers are removed; no progress is made.
        """
        previous_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE) |
                     self._create_servers(2, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE)),
            lb_connections=pset([])
        )
        desired_state = DesiredServerGroupState(
            server_config=pmap(),
            capacity=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 0)


class DiagnoseTests(SynchronousTestCase):
    """
    Tests for :func:`diagnose`.
    """
    def test_diagnose_wraps_connection_and_api_errors(self):
        """
        :func:`diagnose` wraps only :class:`ConnectionRefusedError` and
        :class:`APIError`
        """
        af = fail(APIError(200, {}))
        f = self.failureResultOf(diagnose("system", "operation")(lambda: af)(),
                                 UpstreamError)
        self.assertTrue(f.value.reason.check(APIError))
        self.assertEqual(f.value.system, "system")
        self.assertEqual(f.value.operation, "operation")

        cf = fail(ConnectionRefusedError('meh'))
        f = self.failureResultOf(diagnose("system", "operation")(lambda: cf)(),
                                 UpstreamError)
        self.assertTrue(f.value.reason.check(ConnectionRefusedError))
        self.assertEqual(f.value.system, "system")
        self.assertEqual(f.value.operation, "operation")

        of = fail(ValueError('not-wrapped'))
        self.failureResultOf(diagnose("system", "operation")(lambda: of)(),
                             ValueError)

    def test_diagnose_unwraps_first_error_if_apierr_or_connection_error(self):
        """
        :func:`diagnose` unwraps :class:`FirstError`, no matter how deeply
        nested, and wraps the underlying :class:`ConnectionRefusedError` and
        :class:`APIError` in an :class:`UpstreamError`
        """
        def _wrap(exception):
            return lambda: fail(
                FirstError(
                    Failure(FirstError(Failure(exception), 0)),
                    0))

        f = self.failureResultOf(
            diagnose("system", "operation")(_wrap(APIError(200, {})))(),
            UpstreamError)
        self.assertTrue(f.value.reason.check(APIError))
        self.assertEqual(f.value.system, "system")
        self.assertEqual(f.value.operation, "operation")

        f = self.failureResultOf(
            diagnose("system", "operation")(
                _wrap(ConnectionRefusedError('meh')))(),
            UpstreamError)
        self.assertTrue(f.value.reason.check(ConnectionRefusedError))
        self.assertEqual(f.value.system, "system")
        self.assertEqual(f.value.operation, "operation")

    def test_diagnose_keeps_first_error_if_not_apierr_or_connection_err(self):
        """
        :func:`diagnose` keeps the original :class:`FirstError`, if
        the ultimately underlying exception is not a
        :class:`ConnectionRefusedError` or :class:`APIError`
        """
        err = FirstError(
            Failure(FirstError(Failure(ValueError), 0)),
            0
        )
        f = self.failureResultOf(
            diagnose("system", "operation")(lambda: fail(err))(), FirstError)

        self.assertIs(f.value, err)
