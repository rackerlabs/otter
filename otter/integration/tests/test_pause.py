"""
Tests covering `../groups/groupId/pause` and `../groups/groupId/resume`
endpoints
"""

from twisted.trial import unittest


timeout_default = 600


class PauseTests(unittest.TestCase):
    """
    Tests for `../groups/groupId/pause` endpoint
    """

    def test_pause_stops_convergence(self):
        """
        Pausing a group will stop any further convergence cycle. We do this by
        1. Setup mimic to keep
        2. Creating a group with CLB and 1 min entity
        3.
        """

    def test_pause_and_execute_policy(self):
        """
        Executing any policy of a paused group will result in 403
        """

    def test_pause_and_converge(self):
        """
        Calling `../groups/groupId/converge` on a paused group will result
        in 403
        """

    def test_pause_and_scheduled_policy(self):
        """
        A scheduled policy is not executed on a paused group
        """

    def test_delete_paused_group(self):
        """
        Deleting a paused froup with force=false results in 403
        """

    def test_force_delete_paused_group(self):
        """
        Deleting a paused froup with force=true succeeds
        """
