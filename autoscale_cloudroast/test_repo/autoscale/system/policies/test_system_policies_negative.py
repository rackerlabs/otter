"""
System tests for scaling policies negative scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScalingPoliciesNegativeFixture(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScalingPoliciesNegativeFixture, cls).setUpClass()

    def setUp(self):
        """
        Create a scaling group with minentities = maxentities, scale up by 2
        """
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Delete scaling group
        """
        self.empty_scaling_group(self.group)

    def test_system_execute_policy_when_maxentities_equals_minentities(self):
        """
        Update minentities=maxentities and verify execution of a scale up policy
        """
        self._update_group_min_equals_max(self.group)
        policy_up = {'change': 2}
        policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(policy['execute_response'], 403,
                          msg='scale up policy was executed when minentities = maxentities: %s'
                          % policy['execute_response'])

    def test_system_execute_scale_down_on_newly_created_group_with_minentities(self):
        """
        Update minentities=maxentities and verify execution of a scale down policy
        """
        self._update_group_min_equals_max(self.group)
        policy_down = {'change': -2}
        policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(policy['execute_response'], 403,
                          msg='scale down policy was executed such that active servers < minentities: %s'
                          % policy['execute_response'])

    def test_system_delete_policy_during_execution(self):
        """
        Verify policy excution is not paused when policy is deleted during execution
        """
        policy_up = {'change': 2}
        policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        delete_policy = self.autoscale_client.delete_scaling_policy(
            self.group.id,
            policy['policy_id'])
        self.assertEquals(delete_policy.status_code, 204,
                          msg='Deleting the scaling policy while its executing failed %s'
                          % delete_policy.status_code)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities + policy_up['change'])
        self.assertEquals(len(
            active_servers_list), self.group.groupConfiguration.minEntities + policy_up['change'])

    def _update_group_min_equals_max(self, group):
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=group.groupConfiguration.minEntities,
            metadata={})
        self.assertEquals(update_group.status_code, 204,
                          msg='Updating group config to have minentities=maxentities failed: %s'
                          % update_group.status_code)
