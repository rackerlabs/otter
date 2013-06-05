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

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(ScalingPoliciesNegativeFixture, cls).tearDownClass()

    def test_system_policy_cooldown_different_policies(self):
        """
        Verify the policy cooldown times are not enforced when executing different policies
        """
        pass

    def test_system_execute_policy_when_maxentities_equals_minentities(self):
        """
        Verify execute policy when max entities are equal to min entities
        """
        minentities = maxentities = 1
        splist = [{
            'name': 'scale up by 2',
            'change': 2,
            'cooldown': 0,
            'type': 'webhook'
        }]
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            sp_list=splist)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.get_policy_properties(
            group.scalingPolicies)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 403,
                          msg='scaling policy was executed with status %s'
                          % execute_policy_response.status_code)

    def test_system_execute_scale_down_on_newly_created_group_with_minentities(self):
        """
        Verify executing scale down on a newly created scaling group
        """
        pass

    def test_system_update_minentities_and_scale_down(self):
        """
        Verify scaling group when minentities is reduced. Execute scale down
        """
        pass

    def test_system_delete_policy_during_execution(self):
        """
        Verify deletion on a scaling policy during execution
        """
        pass
