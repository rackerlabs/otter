"""
System Integration tests autoscaling with repose
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class AutoscaleReposeFixture(ScalingGroupWebhookFixture):

    """
    System tests to verify repose integration with autoscale
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(AutoscaleReposeFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(AutoscaleReposeFixture, cls).tearDownClass()

    def test_set_rate_limits(self):
        """
        Verify the rate limit set for autoscale in repose
        """
        pass

    def test_verify_rate_limits(self):
        """
        Verify the rate limit are met when the calls are executed to the limit
        """
        pass
