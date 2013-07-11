"""
System tests for delete scaling group
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteGroupTest(AutoscaleFixture):

    """
    System tests to verify various delete scaling group scenarios
    """

    def setUp(self):
        """
        Create 2 scaling groups, one with minentities>0 with a scaling up policy and webhook
        another with minentities=0
        """
        super(DeleteGroupTest, self).setUp()
        self.create_group0_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=0)
        self.group0 = self.create_group0_response.entity
        self.assertEquals(self.create_group0_response.status_code, 201)
        self.policy_up_execute = {'change': 2}
        self.policy_webhook = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group0.id,
            policy_data=self.policy_up_execute,
            execute_policy=False)
        self.create_group1_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt)
        self.group1 = self.create_group1_response.entity
        self.assertEquals(self.create_group1_response.status_code, 201)
        self.resources.add(self.group0.id,
                           self.autoscale_client.delete_scaling_group)
        self.resources.add(self.group1.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Empty the scaling groups by setting min and maxentities=0 and delete groups
        """
        super(DeleteGroupTest, self).tearDown()
        self.empty_scaling_group(self.group0)
        self.empty_scaling_group(self.group1)

    def test_system_delete_group_with_minentities_over_zero(self):
        """
        A scaling group cannot be deleted when minentities > zero
        """
        self.verify_group_state(
            self.group1.id, self.group1.groupConfiguration.minEntities)
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group1.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group {0} while servers were building on the group'
                          .format(self.group1.id))

    def test_system_delete_group_update_minentities_to_zero(self):
        """
        When minenetities of the group are updated to be zero,
        the scaling group cannot be deleted if it has active servers
        """
        minentities = 0
        reduce_group_size_response = self.autoscale_client.update_group_config(
            group_id=self.group1.id, name=self.group1.groupConfiguration.name,
            cooldown=self.group1.groupConfiguration.cooldown,
            min_entities=minentities,
            max_entities=self.group1.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(reduce_group_size_response.status_code, 204,
                          msg='Update to 0 minentities failed with reason {0} for group {1}'
                          .format(reduce_group_size_response.content, self.group1.id))
        self.verify_group_state(self.group1.id, self.gc_min_entities_alt)
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group1.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group succeeded when servers exist on the group {0} due to {1}'
                          .format(self.group1.id, delete_group_response.content))

    def test_system_delete_group_with_zero_minentities(self):
        """
        A scaling group of zero minentities and no active servers,
        can be deleted
        """
        self.verify_group_state(self.group0.id, 0)
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group0.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Delete group {0} failed even when group was empty'
                          .format(self.group0.id))

    def test_system_delete_group_zero_minentities_execute_webhook(self):
        """
        Create a scaling group with zero minentities and execute a webhook,
        the group cannot be deleted as it has active servers
        """
        execute_webhook = self.autoscale_client.execute_webhook(
            self.policy_webhook['webhook_url'])
        self.assertEquals(execute_webhook.status_code, 202)
        self.verify_group_state(
            self.group0.id, self.policy_up_execute['change'])
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group0.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group {0} while servers were building on the group'
                          .format(self.group0.id))

    def test_system_delete_group_zero_minentities_execute_policy(self):
        """
        Create a scaling group with zero min entities and execute a scaling policy,
        the group cannot be deleted as it has active servers
        """
        execute_policy = self.autoscale_client.execute_policy(
            group_id=self.group0.id,
            policy_id=self.policy_webhook['policy_id'])
        self.assertEquals(execute_policy.status_code, 202)
        self.verify_group_state(
            self.group0.id, self.policy_up_execute['change'])
        delete_group_response = self.autoscale_client.delete_scaling_group(
            self.group0.id)
        self.assertEquals(delete_group_response.status_code, 403,
                          msg='Deleted group {0} while servers were building on the group'
                          .format(self.group0.id))
