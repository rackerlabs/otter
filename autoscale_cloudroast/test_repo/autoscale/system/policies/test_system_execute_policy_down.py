"""
System tests for execute scale down policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ExecutePoliciesDownTest(AutoscaleFixture):

    """
    System tests to verify execute scale down policies
    """

    def setUp(self):
        """
        Create a scaling group with minentities as 2 and scale up by 2
        """
        super(AutoscaleFixture, self).setUp()
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
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Emptying the scaling group by updating minentities=maxentities=0,
        which is then deleted by the Autoscale fixture's teardown
        """
        super(AutoscaleFixture, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_scale_down_policy_execution_change(self):
        """
        A scale down policy with change can be executed
        """
        policy_down = {'change': - self.policy_up['change']}
        execute_scale_down_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_scale_down_policy[
                          'execute_response'], 202,
                          msg='Scale down policy execution with change for group {0} failed with {1}'
                          .format(self.group.id, execute_scale_down_policy['execute_response']))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_scale_down_policy_execution_change_percent(self):
        """
        A scale down policy with change percent can be executed
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
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=servers_from_scale_down)

    def test_system_scale_down_policy_execution_desired_capacity(self):
        """
        A scale down policy with desired capacity can be executed
        """
        policy_down = {
            'desired_capacity': self.group.groupConfiguration.minEntities}
        execute_desired_capacity_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_desired_capacity_policy[
                          'execute_response'], 202)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=policy_down['desired_capacity'])

    def test_system_execute_scale_down_below_minentities_change(self):
        """
        Executing a scale down when change results in servers less than minentities of
        the scaling group, results in a scaling group with active servers=minentities
        """
        policy_down = {'change': - 100}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: {0}'
                          'for group {1}'
                          .format(execute_change_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_execute_scale_down_below_minentities_change_percent(self):
        """
        Executing a scale down when change percent results in servers less than minentities of
        the scaling group, results in a scaling group with active servers=minentities
        """
        policy_down = {'change_percent': - 300}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: {0}'
                          ' for group {1}'
                          .format(execute_change_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_execute_scale_down_below_minentities_desired_capacity(self):
        """
        Executing a scale down when desired capacity results in servers less than minentities of
        the scaling group, results in a scaling group with active servers=minentities
        """
        policy_down = {
            'desired_capacity': self.group.groupConfiguration.minEntities - 1}
        execute_change_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_down,
            execute_policy=True)
        self.assertEquals(execute_change_policy['execute_response'], 202,
                          msg='Scale down policy execution failed when minentities limit is met: {0}'
                          ' for group {1}'
                          .format(execute_change_policy['execute_response'], self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)
