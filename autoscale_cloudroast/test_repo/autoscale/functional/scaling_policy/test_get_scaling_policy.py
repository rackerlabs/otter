"""
Test to create and verify get policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class GetScalingPolicy(ScalingGroupPolicyFixture):

    """
    Verify get policy
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with policy with type change percent
        """
        super(GetScalingPolicy, cls).setUpClass(change_percent=100)
        cls.get_policy_response = cls.autoscale_client.get_policy_details(
            cls.group.id, cls.policy['id'])
        cls.get_policy = cls.get_policy_response.entity

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(GetScalingPolicy, cls).tearDownClass()

    def test_get_scaling_policy(self):
        """
        Verify the get policy call for response code 200, headers and data
        """
        self.assertEquals(self.get_policy_response.status_code, 200,
                          msg='Get scaling policy failed with {0}'
                          .format(self.get_policy_response.status_code))
        self.assertTrue(self.get_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(self.get_policy_response.headers)
        self.assertEquals(self.get_policy.id, self.policy['id'],
                          msg='Policy Id is none upon creation')
        self.assertEquals(self.get_policy.links, self.policy['links'],
                          msg='Links for the scaling policy is none')
        self.assertEquals(self.get_policy.name, self.sp_name,
                          msg='Name of the policy did not match')
        self.assertEquals(self.get_policy.cooldown, self.sp_cooldown,
                          msg='Cooldown time in the policy did not match')
        self.assertEquals(self.get_policy.changePercent, 100,
                          msg='Change in the policy did not match')
