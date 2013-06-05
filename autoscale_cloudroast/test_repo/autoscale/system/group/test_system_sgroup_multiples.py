"""
System tests for account with multiple scaling groups
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from decimal import Decimal, ROUND_UP


class ScalingGroupMultiplesTest(AutoscaleFixture):

    """
    System tests to verify multiple groups on an account
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScalingGroupMultiplesTest, cls).setUpClass()
        first_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.first_scaling_group = first_group.entity
        second_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.second_scaling_group = second_group.entity
        third_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.third_scaling_group = third_group.entity
        cls.resources.add(cls.first_scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.resources.add(cls.second_scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.resources.add(cls.third_scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(ScalingGroupMultiplesTest, cls).tearDownClass()

    def test_system_create_group_with_multiple_policies(self):
        """
        Verify scaling group can have multiple policies
        """
        change = 3
        percentage = 50
        cooldown = 0
        group_response = self.autoscale_behaviors.create_scaling_group_given(gc_cooldown=cooldown)
        group = group_response.entity
        policy1 = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=change,
            sp_cooldown=cooldown)
        policy2 = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        policy3 = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        for each in [policy1, policy2, policy3]:
            execute_policies = self.autoscale_client.execute_policy(group.id, each['id'])
            self.assertEquals(execute_policies.status_code, 202)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        servers_policy1 = self.gc_min_entities + change
        servers_policy2 = servers_policy1 + int((servers_policy1 * (Decimal(percentage) / 100)).to_integral_value(ROUND_UP))
        servers_policy3 = servers_policy2 + int((servers_policy2 * (Decimal(percentage) / 100)).to_integral_value(ROUND_UP))
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            servers_policy3,
            msg="Active + Pending servers are not equal to the total expected servers")
        self.assertEqual(group_state.desiredCapacity, servers_policy3,
                         msg="Desired capacity are not equal to the total expected servers")

    def test_system_create_policy_with_multiple_webhooks(self):
        """
        Verify scaling policy in a group can have multiple multiple_webhooks
        @TODO : fails on dev vm if sleep stmts are not present between all executes
        """

        policy = self.autoscale_behaviors.create_policy_min(
            self.first_scaling_group.id)
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
        execute_webhook1 = self.autoscale_client.execute_webhook(
            webhook_one['links'].capability)
        self.assertEquals(execute_webhook1.status_code, 202)
        execute_webhook2 = self.autoscale_client.execute_webhook(
            webhook_two['links'].capability)
        self.assertEquals(execute_webhook2.status_code, 202)
        execute_webhook3 = self.autoscale_client.execute_webhook(
            webhook_three['links'].capability)
        self.assertEquals(execute_webhook3.status_code, 202)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.first_scaling_group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            self.sp_change,
            msg="Active + Pending servers over first execute policy's change")
        self.assertEqual(group_state.desiredCapacity, self.sp_change,
                         msg="Desired capacity over first execute policy's change")

    def test_system_max_scaling_groups_on_one_account(self):
        """
        Verify the maximum scaling groups an account can have.
        """
        pass

    def test_system_max_policies_on_a_scaling_group(self):
        """
        Verify the maximum scaling policies allowed on a scaling group.
        """
        pass

    def test_system_max_webhooks_on_a_scaling_policy(self):
        """
        Verify the maximum webhooks allowed on a scaling policies.
        """
        pass
