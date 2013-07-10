"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScalingDownExecuteWebhookTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    def setUp(self):
        """
        Create a scaling group with scale up policy and execute its webhook
        """
        super(AutoscaleFixture, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up = {'change': 2}
        self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up,
            execute_webhook=True)
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Emptying the scaling group by updating minentities=maxentities=0,
        which is then deleted by the Autoscale fixture's teardown
        """
        super(AutoscaleFixture, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_execute_webhook_scale_down_change(self):
        """
        Execute a scale down webhook with change as the number
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
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_execute_webhook_scale_down_change_percent(self):
        """
        Execute a webhook with scale down with change percentage 60
        """
        policy_down = {'change_percent': -60}
        execute_webhook_in_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_webhook=True)
        self.assertEquals(execute_webhook_in_change_percent_policy[
                          'execute_response'], 202)
        servers_from_scale_down = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities +
            self.policy_up['change'],
            percentage=policy_down['change_percent'])
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=servers_from_scale_down)

    def test_system_execute_webhook_scale_down_desired_capacity(self):
        """
        Execute a webhook with scale down with desired capacity as the
        minentities of the group
        """
        policy_down = {
            'desired_capacity': self.group.groupConfiguration.minEntities}
        execute_webhook_desired_capacity = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_webhook=True)
        self.assertEquals(execute_webhook_desired_capacity[
                          'execute_response'], 202)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=policy_down['desired_capacity'])
