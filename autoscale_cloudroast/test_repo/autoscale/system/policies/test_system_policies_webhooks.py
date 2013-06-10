"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScalingPolicyWebhookTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScalingPolicyWebhookTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(ScalingPolicyWebhookTest, cls).tearDownClass()

    def test_system_execute_webhook_scale_up_change(self):
        """
        Verify execution to scale up through a webhook, with change
        """
        policy_up = {'change': 1}
        create_group_response = self.autoscale_behaviors.create_scaling_group_min()
        group = create_group_response.entity
        policy_webhook_dict = self.autoscale_behaviors.create_policy_webhook(
            group_id=group.id,
            policy_data=policy_up)
        execute_webhook = self.autoscale_client.execute_webhook(
            policy_webhook_dict['webhook_url'])
        self.assertEquals(execute_webhook.status_code, 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=policy_up['change'])
        self.assertEquals(len(active_servers_list), policy_up[
                          'change'] + self.gc_min_entities)

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
