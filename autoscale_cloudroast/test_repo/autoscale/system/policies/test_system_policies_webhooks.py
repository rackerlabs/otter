"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScalingPolicyWebhookFixture(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScalingPolicyWebhookFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(ScalingPolicyWebhookFixture, cls).tearDownClass()

    def test_system_execute_webhook_scale_up_change(self):
        """
        Verify execution to scale up through a webhook, with change
        """
        pass

    def test_system_execute_webhook_scale_up_change_percent(self):
        """
        Verify execution to scale up through a webhook, with change percent
        """
        pass

    def test_system_execute_webhook_scale_up_desired_capacity(self):
        """
        Verify execution to scale up through a webhook, with desired capacity
        """
        pass

    def test_system_execute_webhook_scale_down_change(self):
        """
        Verify execution to scale down through a webhook, with change
        """
        pass

    def test_system_execute_webhook_scale_down_change_percent(self):
        """
        Verify execution to scale down through a webhook, with change percent
        """
        pass

    def test_system_execute_webhook_scale_down_desired_capacity(self):
        """
        Verify execution to scale down through a webhook, with desired capacity
        """
        pass

    def test_system_update_policy_with_webhook_desired_capacity(self):
        """
        Verify execution of the webhook, with desired capacity after an updates to the policy
        """
        pass
