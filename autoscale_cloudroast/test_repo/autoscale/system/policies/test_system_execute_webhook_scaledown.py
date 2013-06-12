"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.resources import ResourcePool


class ScalingDownExecuteWebhookTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScalingDownExecuteWebhookTest, cls).setUpClass()

    def setUp(self):
        """
        Create a scaling group with scale up policy and execute its webhook
        """
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up = {'change': 2}
        self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up,
            execute_webhook=True)
        self.resource = ResourcePool()
        self.resource.add(self.group.id,
                          self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Delete scaling group
        """
        self.resource.release()

    def test_system_execute_webhook_scale_down_change(self):
        """
        Verify execution of a webhook scale down with change as the number
        at which the setUp scaled up, hence reducing current servers to
        min entities
        """
        policy_down = {'change': - self.policy_up['change']}
        execute_scale_down_webhook = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_webhook=True)
        self.assertEquals(execute_scale_down_webhook[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities)
        self.assertEquals(len(active_servers_list), self.group.groupConfiguration.minEntities)

    def test_system_execute_webhook_scale_down_change_percent(self):
        """
        Verify execution of a webhook, scale down with change percentage 60
        """
        policy_down = {'change_percent': -60}
        execute_webhook_in_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_webhook=True)
        self.assertEquals(execute_webhook_in_change_percent_policy[
                          'execute_response'], 202)
        servers_from_scale_down = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities + self.policy_up['change'],
            percentage=policy_down['change_percent'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=servers_from_scale_down)
        self.assertEquals(len(active_servers_list), servers_from_scale_down)

    def test_system_execute_webhook_scale_down_desired_capacity(self):
        """
        Verify execution of a webhook, scale down with desired capacity as the
        minentities of the group
        """
        policy_down = {'desired_capacity': self.group.groupConfiguration.minEntities}
        execute_webhook_desired_capacity = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_webhook=True)
        self.assertEquals(execute_webhook_desired_capacity[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=policy_down['desired_capacity'])
        self.assertEquals(len(active_servers_list), policy_down['desired_capacity'])
