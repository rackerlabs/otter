"""
System tests for execute policy
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ExecutePoliciesFixture(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ExecutePoliciesFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(ExecutePoliciesFixture, cls).tearDownClass()

    def test_system_policy_cooldown(self):
        """
        Verify the policy cooldown times are enforced
        """
        pass

    def test_system_execute_scale_up_meets_maxentities_change(self):
        """
        Verify scale up policy (change) execution does not exceed maxentities
        """
        pass

    def test_system_execute_scale_down_below_minentities_change(self):
        """
        Verify scale down policy (change) execution does not go below minentities,
        """
        pass

    def test_system_execute_scale_up_meets_maxentities_change_percent(self):
        """
        Verify scale up policy (change_percent) execution does not exceed maxentities
        """
        pass

    def test_system_execute_scale_down_below_minentities_change_percent(self):
        """
        Verify scale down policy (change_percent) execution does not go below minentities,
        """
        pass

    def test_system_execute_scale_up_meets_maxentities_desired_capacity(self):
        """
        Verify scale up policy (desired_capacity) execution does not exceed maxentities
        """
        pass

    def test_system_execute_scale_down_below_minentities_desired_capacity(self):
        """
        Verify scale down policy (desired_capacity) execution does not go below minentities,
        """
        pass

    def test_system_execute_scale_up_down_min_maxentities(self):
        """
        Verify the policy execution does not go below minentities
        """
        pass

    def test_system_scale_up_policy_execution_change(self):
        """
        Verify the execution of a scale up policy with change
        """
        pass

    def test_system_scale_down_policy_execution_change(self):
        """
        Verify the execution of a scale up policy with change
        """
        pass

    def test_system_scale_up_policy_execution_change_percent(self):
        """
        Verify the execution of a scale up policy with change percent
        """
        pass

    def test_system_scale_down_policy_execution_change_percent(self):
        """
        Verify the execution of a scale up policy with change percent
        """
        pass

    def test_system_scale_up_policy_execution_desired_capacity(self):
        """
        Verify the execution of a scale up policy with desired capacity
        """
        pass

    def test_system_scale_down_policy_execution_desired_capacity(self):
        """
        Verify the execution of a scale up policy with desired capacity
        """
        pass

    def test_system_update_policy_to_scale_down(self):
        """
        Verify the execution after scale up policy is updated to scale down
        """
        pass

    def test_system_update_policy_to_scale_up(self):
        """
        Verify the execution after scale down policy is updated to scale up
        """
        pass

    def test_system_scale_up_scale_down_multiple_policies_simaltaneously(self):
        """
        Verify the execution of multiple scale up and scale down policies simaltaneously
        """
        pass

    def test_system_scale_up_scale_down_multiple_policies_in_sequence(self):
        """
        Verify the execution of multiple scale up and scale down policies in sequence
        """
        pass

    def test_system_scale_up_scale_down_all_policy_types(self):
        """
        Verify the execution of multiple scale up and scale down policies of all types
        Eg : execute change, chnage percent, then desired capacity and verify servers at all points
        """
        pass
