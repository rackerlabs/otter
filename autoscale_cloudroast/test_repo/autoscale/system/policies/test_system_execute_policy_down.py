"""
System tests for execute scale down policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.resources import ResourcePool


class ExecutePoliciesDownTest(AutoscaleFixture):

    """
    System tests to verify execute scale down policies
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client, behaviors and configs
        """
        super(ExecutePoliciesDownTest, cls).setUpClass()

    def setUp(self):
        """
        Create a scaling group with minentities as 2 and scale up by 2
        """
        minentities = 2
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up = {'change': 2}
        self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up,
            execute_policy=True)
        self.resource = ResourcePool()
        self.resource.add(self.group.id,
                          self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Delete scaling group
        """
        self.resource.release()

    def test_system_scale_down_policy_execution_change(self):
        """
        Verify the execution of a scale down policy with change
        """
        policy_down = {'change': - self.policy_up['change']}
        execute_scale_down_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_scale_down_policy[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities)
        self.assertEquals(len(
            active_servers_list), self.group.groupConfiguration.minEntities)

    def test_system_scale_down_policy_execution_change_percent(self):
        """
        Verify the execution of a scale down policy with change percent
        """
        policy_down = {'change_percent': -60}
        execute_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_percent_policy[
                          'execute_response'], 202)
        servers_from_scale_down = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities +
            self.policy_up['change'],
            percentage=policy_down['change_percent'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=servers_from_scale_down)
        self.assertEquals(len(active_servers_list), servers_from_scale_down)

    def test_system_scale_down_policy_execution_desired_capacity(self):
        """
        Verify the execution of a scale down policy with desired capacity
        """
        policy_down = {
            'desired_capacity': self.group.groupConfiguration.minEntities}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_desired_capacity_policy[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=policy_down['desired_capacity'])
        self.assertEquals(len(
            active_servers_list), policy_down['desired_capacity'])

    def test_system_execute_scale_down_below_minentities_change(self):
        """
        Verify execution of scale down policy when change results in servers less than
        minentities of the scaling group
        """
        policy_down = {'change': - (1 + self.policy_up['change'] +
                                    self.group.groupConfiguration.minEntities)}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: %s'
                          % execute_change_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.minEntities,
            msg='Active servers on group after scaling down below min entities are not as expected')

    def test_system_execute_scale_down_below_minentities_change_percent(self):
        """
        Verify execution of scale down policy when change percent results in servers less than
        minentities of the scaling group
        """
        policy_down = {'change_percent': - 300}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: %s'
                          % execute_change_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.minEntities,
            msg='Active servers on group after scaling down below min entities are not as expected')

    def test_system_execute_scale_down_below_minentities_desired_capacity(self):
        """
        Verify execution of scale down policy when desired capacity less than minentities
        of the scaling group
        """
        policy_down = {'desired_capacity': self.group.groupConfiguration.minEntities - 1}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: %s'
                          % execute_change_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.minEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.minEntities,
            msg='Active servers on group after scaling down below min entities are not as expected')
