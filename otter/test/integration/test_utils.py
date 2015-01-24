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
    def _create_servers(self, n):
        """
        Create some dummy test servers.
        """
        return pset([
            NovaServer(
                id=str(i),
                state=ServerState.ACTIVE,
                created=123456789.)
            for i in xrange(n)
        ])

    def test_capacity_closer_to_desired_when_scaling_up(self):
        """
        If the capacity moves closer to the desired, progress has been
        made.
        """
        previous_state = GroupState(
            servers=self._create_servers(2),
            lb_connections=pset([]) # TODO: servers should already be attached to their load balancers
        )
        current_state = GroupState(
            servers=self._create_servers(4),
            lb_connections=pset([]) # TODO: old servers should still be attached
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
            lb_connections=pset([]) # TODO: servers should already be attached to their load balancers
        )
        current_state = GroupState(
            servers=self._create_servers(2),
            lb_connections=pset([]) # TODO: old servers should still be attached
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
            lb_connections=pset([]) # TODO: servers should already be attached to their load balancers
        )
        current_state = GroupState(
            servers=self._create_servers(6),
            lb_connections=pset([]) # TODO: old servers should still be attached
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        self.assertRaises(
            AssertionError,
            measure_progress, previous_state, current_state, desired_state)
