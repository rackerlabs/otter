"""
System tests for execute multiple policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep


class ExecuteMultiplePoliciesTest(AutoscaleFixture):

    """
    System tests to verify execute multiple scaling policies' scenarios
    """

    def setUp(self):
        """
        Create a scaling group with minentities > 0, with multiple scaling policies
        and execute one scale up policy to create 2 servers
        """
        super(ExecuteMultiplePoliciesTest, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.change = 2
        self.change_percent = 50
        self.cooldown = 1
        self.policy_up_change = self.autoscale_behaviors.create_policy_given(
            group_id=self.group.id, sp_change=self.change, sp_cooldown=self.cooldown)
        self.policy_down_change = self.autoscale_behaviors.create_policy_given(
            group_id=self.group.id, sp_change=-(self.change - 1), sp_cooldown=self.cooldown)
        self.policy_up_change_percent = self.autoscale_behaviors.create_policy_given(
            group_id=self.group.id, sp_change_percent=self.change_percent, sp_cooldown=self.cooldown)
        self.policy_down_change_percent = self.autoscale_behaviors.create_policy_given(
            group_id=self.group.id,
            sp_change_percent=-(self.change_percent),
            sp_cooldown=self.cooldown)
        self.policy_desired_capacity = self.autoscale_behaviors.create_policy_given(
            group_id=self.group.id,
            sp_desired_capacity=self.group.groupConfiguration.minEntities,
            sp_cooldown=self.cooldown)
        self.policy_up_execute = {
            'change': self.change, 'cooldown': self.cooldown}
        self.policy_executed = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up_execute,
            execute_policy=True)
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Emptying the scaling group by updating minentities=maxentities=0,
        which is then deleted by the Autoscale fixture's teardown
        """
        super(ExecuteMultiplePoliciesTest, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_policy_up_cooldown(self):
        """
        Execute a scale up policy with cooldown > 0 more than once within the cooldown period,
        and policy execution fails when cooldown is not met
        """
        execute_on_cooldown = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_executed['policy_id'])
        self.assertEquals(execute_on_cooldown.status_code, 403,
                          msg='Scale up policy executed sucessfully for group {0}'
                          ' when cooldown is not met: {1}'
                          .format(self.group.id, execute_on_cooldown.status_code))

    def test_system_policy_down_cooldown(self):
        """
        Execute a scale down policy with cooldown > 0 more than once within the cooldown period,
        and policy execution fails when cooldown is not met
        """
        execute_scale_down = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_down_change['id'])
        self.assertEquals(execute_scale_down.status_code, 202,
                          msg='Policy down failed to execute for group {0} with {1}'
                          .format(self.group.id, execute_scale_down.status_code))
        execute_on_cooldown = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_down_change['id'])
        self.assertEquals(execute_on_cooldown.status_code, 403,
                          msg='Scale down policy executed when cooldown is not met with {0}'
                          ' for group {1}'
                          .format(execute_on_cooldown.status_code, self.group.id))

    def test_system_execute_different_policies_simaltaneously(self):
        """
        The policy cooldown times are not enforced when executing different policies,
        and executing such polcies result in active servers as expected
        """
        execute_change_percent_scale_up = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_up_change_percent['id'])
        self.assertEquals(execute_change_percent_scale_up.status_code, 202,
                          msg='Scale up policy execution for group {0} failed with {1}'
                          .format(self.group.id, execute_change_percent_scale_up.status_code))
        execute_change_scale_down = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_down_change['id'])
        self.assertEquals(execute_change_scale_down.status_code, 202,
                          msg='Scale down policy execution for group {0} failed with {1}'
                          .format(self.group.id, execute_change_scale_down.status_code))
        execute_desired_capacity_scale = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_desired_capacity['id'])
        self.assertEquals(execute_desired_capacity_scale.status_code, 202,
                          msg='Policy with desired capacity=minentities failed to execute with {0}'
                          ' for group {1}'
                          .format(execute_desired_capacity_scale.status_code, self.group.id))
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def test_system_scale_up_scale_down_multiple_policies_in_sequence(self):
        """
        Different scale up and scale down policies on the scaling group can be executed
        in sequence after each policy's cooldown time
        """
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_executed['policy_id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_up_change['id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_down_change['id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_down_change['id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_up_change_percent['id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_down_change_percent['id'])
        self._execute_policy_after_cooldown(
            self.group.id, self.policy_desired_capacity['id'])
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities)

    def _execute_policy_after_cooldown(self, group_id, policy_id):
        """
        After the cooldown period, executes the policy and asserts if the policy
        was executed successfully
        """
        sleep(self.cooldown)
        execute_policy = self.autoscale_client.execute_policy(
            self.group.id,
            policy_id)
        self.assertEquals(execute_policy.status_code, 202,
                          msg='Execution of the policy after cooldown failed with {0} for group {1}'
                          .format(execute_policy.status_code, self.group.id))
