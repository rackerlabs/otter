"""
System tests to test execute webhook after the policy is updated
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep


class UpdatePoliciesExecuteWebhookTest(AutoscaleFixture):

    """
    System tests to verify executing webhooks for updated scaling policies.
    """

    def setUp(self):
        """
        Create a scaling group with min entities > 0, scale up with cooldown 1 sec
        """
        super(UpdatePoliciesExecuteWebhookTest, self).setUp()
        self.cooldown = 1
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up = {'change': 2, 'cooldown': self.cooldown}
        self.policy = self.autoscale_behaviors.create_policy_webhook(
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
        super(UpdatePoliciesExecuteWebhookTest, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_update_scale_up_execute_webhook(self):
        """
        Update a scale up policy and verify execution of such a policy using its webhook
        """
        change = self.policy_up['change'] + 1
        sleep(self.cooldown)
        upd_scale_up_execute_webhook = self._update_policy_execute_webhook(
            self.group.id,
            self.policy['policy_id'], change, self.policy['webhook_url'])
        self.assertEquals(upd_scale_up_execute_webhook, 202,
                          msg='Executing the updated scale up policy using the webhook failed with {0}'
                          'for group {1}'
                          .format(upd_scale_up_execute_webhook, self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities +
            self.policy_up['change'] + change)

    def test_system_update_scale_up_to_scale_down_execute_webhook(self):
        """
        Update a scale up policy to scale down by the same change value and verify execution
        of such a policy using its webhook
        """
        change = - self.policy_up['change']
        sleep(self.cooldown)
        upd_to_scale_down_execute_webhook = self._update_policy_execute_webhook(
            self.group.id,
            self.policy['policy_id'], change, self.policy['webhook_url'])
        self.assertEquals(upd_to_scale_down_execute_webhook, 202,
                          msg='Executing the updated scale down policy failed with {0} for group {1}'
                          .format(upd_to_scale_down_execute_webhook, self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_update_policy_from_change_to_change_percent_scale_down_execute_webhook(self):
        """
        Update the existing scale up policy from change to change percent,such that
        is scales down by 50%. Execute the webhook to execute the updated policy.
        """
        upd_change_percent = - 50
        sleep(self.cooldown)
        upd_policy_to_change_percent_capacity_execute_webhook = self._update_policy_cp_execute_webhook(
            self.group.id,
            self.policy['policy_id'], upd_change_percent, self.policy['webhook_url'])
        self.assertEquals(upd_policy_to_change_percent_capacity_execute_webhook, 202,
                          msg='Executing the updated policy using the webhook failed with {0}'
                          ' for group {1}'
                          .format(upd_policy_to_change_percent_capacity_execute_webhook, self.group.id))
        servers_from_scale_down = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities +
            self.policy_up['change'],
            percentage=upd_change_percent)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=servers_from_scale_down)

    def _update_policy_cp_execute_webhook(self, group_id, policy_id, policy_data, webhook_url):
        """
        Updates any given policy to change percent and executes the webhook.
        Returns the response code of the updated policy's execution
        """
        get_policy = self.autoscale_client.get_policy_details(
            group_id, policy_id)
        policy_b4_update = get_policy.entity
        self.autoscale_client.update_policy(
            group_id=group_id,
            policy_id=policy_id,
            name=policy_b4_update.name,
            cooldown=policy_b4_update.cooldown,
            change_percent=policy_data,
            policy_type=policy_b4_update.type)
        execute_upd_policy_using_webhook = self.autoscale_client.execute_webhook(
            webhook_url)
        return execute_upd_policy_using_webhook.status_code

    def _update_policy_execute_webhook(self, group_id, policy_id, policy_data, webhook_url):
        """
        Updates any given policy to change and executes the webhook.
        Returns the response code of the updated policy's execution
        """
        get_policy = self.autoscale_client.get_policy_details(
            group_id, policy_id)
        policy_b4_update = get_policy.entity
        self.autoscale_client.update_policy(
            group_id=group_id,
            policy_id=policy_id,
            name=policy_b4_update.name,
            cooldown=policy_b4_update.cooldown,
            change=policy_data,
            policy_type=policy_b4_update.type)
        execute_upd_policy_using_webhook = self.autoscale_client.execute_webhook(
            webhook_url)
        return execute_upd_policy_using_webhook.status_code
