"""
Tests for trigger_convergence.py
"""

from trigger_convergence import trigger_convergence_groups

from twisted.internet.defer import fail, succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.test.utils import patch


class TriggerConvergenceGroupsTests(SynchronousTestCase):
    """
    Tests for :func:`trigger_convergence_groups`
    """

    def setUp(self):
        self.mock_tg = patch(self, "trigger_convergence.trigger_convergence")
        self.groups = [{"tenantId": "t1", "groupId": "g1"},
                       {"tenantId": "t2", "groupId": "g2"}]

    def test_success(self):
        self.mock_tg.side_effect = [succeed(None), succeed(None)]
        self.assertEqual(
            self.successResultOf(
                trigger_convergence_groups("a", "r", self.groups, 2, False)),
            [])

    def test_with_failure(self):
        err = ValueError("eh")
        self.mock_tg.side_effect = [succeed(None), fail(err)]
        self.assertEqual(
            self.successResultOf(
                trigger_convergence_groups("a", "r", self.groups, 2, False)),
            [("t2", "g2", err)])
