"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags
from time import sleep


class ScalingUpExecuteWebhookTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    def setUp(self):
        """
        Create a scaling group with minentities over zero
        """
        super(ScalingUpExecuteWebhookTest, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt)
        self.group = self.create_group_response.entity
        self.resources.add(self.group, self.empty_scaling_group)

    @tags(speed='quick')
    def test_system_execute_webhook_scale_up_change(self):
        """
        Create a scale up policy with change and execute its webhook
        """
        policy_up = {'change': 1}
        execute_webhook_in_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_webhook=True)
        self.assertEquals(execute_webhook_in_change_policy[
                          'execute_response'], 202)
        sleep(0.1)
        self.check_for_expected_number_of_building_servers(
            group_id=self.group.id,
            expected_servers=policy_up['change'] + self.group.groupConfiguration.minEntities)

    @tags(speed='quick')
    def test_system_execute_webhook_scale_up_change_percent(self):
        """
        Execute a webhook for scale up policy with change percent.
        """
        policy_up = {'change_percent': 100}
        execute_webhook_in_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_webhook=True)
        self.assertEquals(execute_webhook_in_change_percent_policy[
                          'execute_response'], 202)
        servers_from_scale_up = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities,
            percentage=policy_up['change_percent'])
        sleep(0.1)
        self.check_for_expected_number_of_building_servers(
            group_id=self.group.id,
            expected_servers=servers_from_scale_up)

    @tags(speed='quick')
    def test_system_execute_webhook_scale_up_desired_capacity(self):
        """
        Execute a webhook for scale up policy with desired capacity.
        """
        desired_capacity = self.group.groupConfiguration.minEntities + 1
        policy_up = {'desired_capacity': desired_capacity}
        execute_webhook_in_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_webhook=True)
        self.assertEquals(execute_webhook_in_desired_capacity_policy[
                          'execute_response'], 202)
        sleep(0.1)
        self.check_for_expected_number_of_building_servers(
            group_id=self.group.id,
            expected_servers=policy_up['desired_capacity'])
