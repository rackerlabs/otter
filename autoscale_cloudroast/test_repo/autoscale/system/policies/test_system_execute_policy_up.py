"""
System tests for execute policy
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ExecutePoliciesUpTest(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    def setUp(self):
        """
        Create a scaling group with minentities over zero and maxentities two times minentities
        """
        super(ExecutePoliciesUpTest, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_max_entities=self.gc_min_entities_alt * 2)
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Emptying the scaling group by updating minentities=maxentities=0,
        which is then deleted by the Autoscale fixture's teardown
        """
        super(ExecutePoliciesUpTest, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_scale_up_policy_execution_change(self):
        """
        A scale up policy with change can be executed
        """
        policy_up = {'change': 1}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_change_policy[
                          'execute_response'], 202)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=policy_up['change'] + self.group.groupConfiguration.minEntities)

    def test_system_scale_up_policy_execution_change_percent(self):
        """
        A scale up policy with change percent can be executed
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
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=servers_from_scale_up)

    def test_system_scale_up_policy_execution_desired_capacity(self):
        """
        A scale up policy with desired capacity can be executed
        """
        desired_capacity = self.group.groupConfiguration.maxEntities
        policy_up = {'desired_capacity': desired_capacity}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_desired_capacity_policy[
                          'execute_response'], 202)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=policy_up['desired_capacity'])

    def test_system_execute_scale_up_meets_maxentities_change(self):
        """
        Executing a scale up policy when change exceeds maxentities of the scaling group,
        results in a scaling group with active servers=maxentities
        """
        policy_up = {'change': self.group.groupConfiguration.maxEntities}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale up policy execution failed when change exceeds maxentities '
                          'with {0} for group {1}'
                          .format(execute_change_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.maxEntities)

    def test_system_execute_scale_up_meets_maxentities_change_percent(self):
        """
        Executing a scale up policy when change percent exceeds maxentities of the scaling group,
        results in a scaling group with active servers=maxentities
        """
        policy_up = {'change_percent': 300}
        execute_change_percent_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(
            execute_change_percent_policy['execute_response'], 202,
            msg='Scale up execution failed when changepercent exceeds maxentities with {0}'
            ' for group {1}'
            .format(execute_change_percent_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.maxEntities)

    def test_system_execute_scale_up_meets_maxentities_desired_capacity(self):
        """
        Executing a scale up policy when desired capacity exceeds maxentities of the scaling group,
        results in a scaling group with active servers=maxentities
        """
        policy_up = {
            'desired_capacity': self.group.groupConfiguration.maxEntities + 1}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(
            execute_desired_capacity_policy['execute_response'], 202,
            msg='Scale up execution failed when desiredcapacity over maxentities with {0}'
            ' for group {1}'
            .format(execute_desired_capacity_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.maxEntities)
