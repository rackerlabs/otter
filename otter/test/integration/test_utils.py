"""
Tests for the utility functions for convergence black-box testing.
"""

from pyrsistent import pmap, pset

from otter.convergence.model import (
    NovaServer,
    DesiredGroupState,
    ServerState
)
from otter.test.integration.utils import (
    GroupState,
    measure_progress
)

from twisted.trial.unittest import SynchronousTestCase


class MeasureProgressTests(SynchronousTestCase):
    """
    Tests for :func:`measure_progress`.
    """
    def _create_servers(self, n, state=ServerState.ACTIVE):
        """
        Create some dummy test servers.
        """
        return pset([
            NovaServer(id=str(i), state=state, created=123456789.)
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
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
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
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=1,
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
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        self.assertRaises(
            AssertionError,
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
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        self.assertRaises(
            AssertionError,
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
            servers=(self._create_servers(2, state=ServerState.ACTIVE)
                     | self._create_servers(2, state=ServerState.BUILD)),
            lb_connections=pset([])
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
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
            servers=(self._create_servers(1, state=ServerState.ACTIVE)
                     | self._create_servers(2, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
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
            servers=(self._create_servers(1, state=ServerState.ACTIVE)
                     | self._create_servers(1, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 0)

    def test_reaping_errored_servers(self):
        """
        Errored servers are removed; no progress is made.
        """
        previous_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE)
                     | self._create_servers(2, state=ServerState.ERROR)),
            lb_connections=pset([])
        )
        current_state = GroupState(
            servers=(self._create_servers(1, state=ServerState.ACTIVE)),
            lb_connections=pset([])
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 0)
