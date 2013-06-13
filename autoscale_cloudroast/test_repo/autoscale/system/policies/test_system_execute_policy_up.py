"""
System tests for execute policy
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ExecutePoliciesUpTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ExecutePoliciesUpTest, cls).setUpClass()

    def setUp(self):
        """
        Create a scaling group with minentities over zero and maxentities two times minentities
        """
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_max_entities=self.gc_min_entities_alt * 2)
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Delete scaling group
        """
        self.empty_scaling_group(self.group)

    def test_system_scale_up_policy_execution_change(self):
        """
        Verify the execution of a scale up policy with change
        """
        policy_up = {'change': 1}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_change_policy[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=policy_up['change'] + self.group.groupConfiguration.minEntities)
        self.assertEquals(len(active_servers_list), policy_up[
                          'change'] + self.group.groupConfiguration.minEntities)

    def test_system_scale_up_policy_execution_change_percent(self):
        """
        Verify the execution of a scale up policy with change percent
        """
        policy_up = {'change_percent': 50}
        execute_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_change_percent_policy[
                          'execute_response'], 202)
        servers_from_scale_up = self.autoscale_behaviors.calculate_servers(
            current=self.group.groupConfiguration.minEntities,
            percentage=policy_up['change_percent'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=servers_from_scale_up)
        self.assertEquals(len(active_servers_list), servers_from_scale_up)

    def test_system_scale_up_policy_execution_desired_capacity(self):
        """
        Verify the execution of a scale up policy with desired capacity
        """
        desired_capacity = self.group.groupConfiguration.maxEntities
        policy_up = {'desired_capacity': desired_capacity}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_desired_capacity_policy[
                          'execute_response'], 202)
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=policy_up['desired_capacity'])
        self.assertEquals(len(active_servers_list),
                          policy_up['desired_capacity'])

    def test_system_execute_scale_up_meets_maxentities_change(self):
        """
        Verify execution of scale up policy when change exceeds maxentities
        of the scaling group
        """
        policy_up = {'change': self.group.groupConfiguration.maxEntities}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale up policy execution failed when change exceeds maxentities with %s'
                          % execute_change_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.maxEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.maxEntities,
            msg='Active servers on group after scale up policy execution is not as expected')

    def test_system_execute_scale_up_meets_maxentities_change_percent(self):
        """
        Verify execution of scale up policy when change percent exceeds maxentities
        of the scaling group
        """
        policy_up = {'change_percent': 300}
        execute_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(
            execute_change_percent_policy['execute_response'], 202,
            msg='Scale up execution failed when changepercent exceeds maxentities with %s'
            % execute_change_percent_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.maxEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.maxEntities,
            msg='Active servers on group after scale up policy execution is not as expected')

    def test_system_execute_scale_up_meets_maxentities_desired_capacity(self):
        """
        Verify execution of scale up policy when desired capacity exceeds maxentities
        of the scaling group by 1
        """
        policy_up = {
            'desired_capacity': self.group.groupConfiguration.maxEntities + 1}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(
            execute_desired_capacity_policy['execute_response'], 202,
            msg='Scale up execution failed when desiredcapacity over maxentities with %s'
            % execute_desired_capacity_policy['execute_response'])
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=self.group.id,
            active_servers=self.group.groupConfiguration.maxEntities)
        self.assertEquals(
            len(active_servers_list), self.group.groupConfiguration.maxEntities,
            msg='Active servers on group after scale up policy execution is not as expected')
