"""
System tests for account with multiple scaling groups
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
#from time import sleep


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

    def test_system_create_delete_multiple_scaling_groups(self):
        """
        Verify multiple scaling groups can be created and deleted
        """
        pass

    def test_system_create_group_with_multiple_policies(self):
        """
        Verify scaling group can have multiple policies
        """
        pass

    def test_system_create_policy_with_multiple_webhooks(self):
        """
        Verify scaling policy in a group can have multiple multiple_webhooks
        @TODO : remove the waitimes after zoo keeper locks are enforced
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
        #sleep(3)
        self.assertEquals(execute_webhook1.status_code, 202)
        execute_webhook2 = self.autoscale_client.execute_webhook(
            webhook_two['links'].capability)
        self.assertEquals(execute_webhook2.status_code, 202)
        #sleep(3)
        execute_webhook3 = self.autoscale_client.execute_webhook(
            webhook_three['links'].capability)
        self.assertEquals(execute_webhook3.status_code, 202)
        #sleep(3)
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
