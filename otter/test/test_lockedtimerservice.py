"""
Tests for `LockedTimerService`
"""

class FakeTimerFunc(ILockedTimerFunc):
    def __init__(self, testcase):
        self.testcase = testcase

class LTSService(SynchronousTestCase):
    """
    Tests for :obj:`LockedTimerService`
    """

    def setUp(self):
        self.clock = Clock()
        self.log = mock_log()
        self.lb, lock = create_fake_lock()
        self.func = iMock(ILockedTimerFunc)
        self.s = lts.LockedTimerService(
            self.clock, "disp", "/path", 10, self.func, lock=lock)

    def
