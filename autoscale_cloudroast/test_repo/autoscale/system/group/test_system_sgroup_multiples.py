"""
System tests for account with multiple scaling groups
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScalingGroupMultiplesTest(AutoscaleFixture):

    """
    System tests to verify multiple groups on an account
    """

    def setUp(self):
        """
        Create 3 scaling groups
        """
        super(ScalingGroupMultiplesTest, self).setUp()
        first_group = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=0)
        self.first_scaling_group = first_group.entity
        second_group = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=0)
        self.second_scaling_group = second_group.entity
        third_group = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=0)
        self.third_scaling_group = third_group.entity
        self.resources.add(self.first_scaling_group.id,
                           self.autoscale_client.delete_scaling_group)
        self.resources.add(self.second_scaling_group.id,
                           self.autoscale_client.delete_scaling_group)
        self.resources.add(self.third_scaling_group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Delete scaling groups
        """
        super(ScalingGroupMultiplesTest, self).tearDown()
        self.empty_scaling_group(self.first_scaling_group)
        self.empty_scaling_group(self.second_scaling_group)
        self.empty_scaling_group(self.third_scaling_group)

    def test_system_create_group_with_multiple_policies(self):
        """
        Scaling group can have multiple policies and can be executed
        """
        change = 3
        percentage = 50
        cooldown = 0
        policy1 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change=change,
            sp_cooldown=cooldown)
        policy2 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        policy3 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        for each in [policy1, policy2, policy3]:
            execute_policies = self.autoscale_client.execute_policy(
                self.first_scaling_group.id, each['id'])
            self.assertEquals(execute_policies.status_code, 202,
                              msg='Policy execution failed for group {0} with {1}'.format(
                              self.first_scaling_group.id, execute_policies.status_code))
        sp1 = self.gc_min_entities + change
        sp2 = self.autoscale_behaviors.calculate_servers(sp1, percentage)
        sp3 = self.autoscale_behaviors.calculate_servers(sp2, percentage)
        self.verify_group_state(self.first_scaling_group.id, sp3)

    def test_system_create_policy_with_multiple_webhooks(self):
        """
        Scaling policy in a group can have multiple webhooks and they can be
        executed
        """

        policy = self.autoscale_behaviors.create_policy_min(
            group_id=self.first_scaling_group.id,
            sp_cooldown=0)
        webhook_first = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook1')
        webhook_one = self.autoscale_behaviors.get_webhooks_properties(
            webhook_first.entity)
        webhook_second = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook2')
        webhook_two = self.autoscale_behaviors.get_webhooks_properties(
            webhook_second.entity)
        webhook_third = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook3')
        webhook_three = self.autoscale_behaviors.get_webhooks_properties(
            webhook_third.entity)
        for each_webhook in [webhook_one, webhook_two, webhook_three]:
            execute_webhook = self.autoscale_client.execute_webhook(
                each_webhook['links'].capability)
            self.assertEquals(execute_webhook.status_code, 202,
                              msg='Policy webhook execution failed for group {0} with {1}'.format(
                              self.first_scaling_group.id, execute_webhook.status_code))
        self.verify_group_state(
            self.first_scaling_group.id, (self.sp_change * 3))

    def test_system_max_scaling_groups_on_one_account(self):
        """
        The maximum scaling groups an account can have are 100.
        """
        pass

    def test_system_max_policies_on_a_scaling_group(self):
        """
        The maximum scaling policies allowed on a scaling group are XXX.
        """
        pass

    def test_system_max_webhooks_on_a_scaling_policy(self):
        """
        The maximum webhooks allowed on a scaling policy are XXX.
        """
        pass
