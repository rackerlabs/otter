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
    def test_capacity_closer_to_desired(self):
        """
        If the capacity moves closer to the desired, progress has been
        made.
        """
        previous_state = GroupState(
            servers=pset([
                NovaServer(
                    id=str(i),
                    state=ServerState.ACTIVE,
                    created=123456789.)
                for i in xrange(2)
            ]),
            lb_connections=pset([]) # TODO: servers should already be attached to their load balancers
        )
        current_state = GroupState(
            servers=pset([
                NovaServer(
                    id=str(i),
                    state=ServerState.ACTIVE,
                    created=123456789.)
                for i in xrange(4)
            ]),
            lb_connections=pset([]) # TODO: old servers should still be attached
        )
        desired_state = DesiredGroupState(
            launch_config=pmap(),
            desired=5,
        )
        progress = measure_progress(
            previous_state, current_state, desired_state)
        self.assertEqual(progress, 2)
