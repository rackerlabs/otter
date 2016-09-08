"""
Tests for `LockedTimerService`
"""

class LTSService(SynchronousTestCase):
    """
    Tests for :obj:`LockedTimerService`
    """

    def setUp(self):
        self.clock = Clock()
        self.log = mock_log()
        self.ggtc = patch(
            self, "otter.convergence.selfheal.get_groups_to_converge",
            side_effect=intent_func("ggtc"))
        self.lb, lock = create_fake_lock()
        self.s = sh.SelfHeal("disp", 300, self.log, self.clock, "cf",
                             lock=lock)
