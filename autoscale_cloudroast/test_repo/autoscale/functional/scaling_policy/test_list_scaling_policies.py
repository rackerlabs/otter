"""
Test to create and verify the listing policies.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class ListScalingPolicies(ScalingGroupPolicyFixture):
    """
    Verify list policies
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with 4 policies
        """
        super(ListScalingPolicies, cls).setUpClass()
        cls.policy1 = cls.policy
        policy2_data = {'change_percent': 100, 'cooldown': 200}
        policy3_data = {'desired_capacity': 3}
        policy4_data = {'change': 6}
        cls.policy2 = cls.autoscale_behaviors.create_policy_webhook(
            cls.group.id, policy2_data)
        cls.policy3 = cls.autoscale_behaviors.create_policy_webhook(
            cls.group.id, policy3_data)
        cls.policy4 = cls.autoscale_behaviors.create_policy_webhook(
            cls.group.id, policy4_data)

    def test_list_scaling_policies(self):
        """
        Verify the list policies call for response code 201, headers and data
        """
        policy_id_list = []
        list_policies_resp = self.autoscale_client.list_policies(self.group.id)
        self.assertEquals(list_policies_resp.status_code, 200,
                          msg='Create webhook for a policy failed with {0} for group'
                          ' {1}'.format(list_policies_resp.status_code, self.group.id))
        self.validate_headers(list_policies_resp.headers)
        for i in list_policies_resp.entity:
            policy_id_list.append(i.id)
        self.assertTrue(self.policy1['id'] in policy_id_list)
        self.assertTrue(self.policy2['policy_id'] in policy_id_list)
        self.assertTrue(self.policy3['policy_id'] in policy_id_list)
        self.assertTrue(self.policy4['policy_id'] in policy_id_list)
