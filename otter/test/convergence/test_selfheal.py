"""
Tests for :mod:`otter.convergence.selfheal`
"""


class SelfHealTests(SynchronousTestCase):
    """
    Tests for :obj:`SelfHeal`
    """

    def setUp(self):
        self.lock = mock.Mock(specs=["acquire", "release"])
        self.kzc = mock.Mock(specs=["Lock"])

    def test_calls_cat(self):
        s = ConvergeAllGroups(disp,

    def test_health_check(self):

    def test_stop_service(self):





