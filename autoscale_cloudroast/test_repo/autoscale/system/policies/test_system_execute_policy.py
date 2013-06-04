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

    def test_system_negative_execute_scale_down_on_newly_created_group(self):
        """
        Verify executing scale down on a newly created scaling group
        """
        pass

    # def test_system_scaling_group_lbaas_draining_disabled(self):
    #     """
    #     Verify execute policy with lbaas draining or disabled
    #     """
    #     pass
