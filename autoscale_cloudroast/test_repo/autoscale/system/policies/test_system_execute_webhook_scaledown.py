"""
System tests for scaling policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags


class ScalingDownExecuteWebhookTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    def setUp(self):
        """
        Create a scaling group with scale up policy and execute its webhook
        """
        super(ScalingDownExecuteWebhookTest, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up = {'change': 2}
        self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up,
            execute_webhook=True)
        self.servers_before_scaledown = self.gc_min_entities_alt + self.policy_up['change']
        self.resources.add(self.group, self.empty_scaling_group)

    @tags(speed='slow')
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
        self.wait_for_expected_group_state(self.group.id,
                                           self.group.groupConfiguration.minEntities)
        self.assert_servers_deleted_successfully(
            self.group.launchConfiguration.server.name,
            self.group.groupConfiguration.minEntities)

    @tags(speed='slow')
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
        self.wait_for_expected_group_state(self.group.id,
                                           servers_from_scale_down)
        self.assert_servers_deleted_successfully(
            self.group.launchConfiguration.server.name,
            servers_from_scale_down)

    @tags(speed='slow')
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
        self.wait_for_expected_group_state(self.group.id,
                                           policy_down['desired_capacity'])
        self.assert_servers_deleted_successfully(
            self.group.launchConfiguration.server.name,
            policy_down['desired_capacity'])
