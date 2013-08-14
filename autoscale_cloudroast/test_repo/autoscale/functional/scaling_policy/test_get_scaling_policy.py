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

    def test_get_scaling_policy(self):
        """
        Verify the get policy call for response code 200, headers and data
        """
        self.assertEquals(self.get_policy_response.status_code, 200,
                          msg='Get scaling policy failed with {0}'
                          .format(self.get_policy_response.status_code))
        self.validate_headers(self.get_policy_response.headers)
        self.assert_get_policy(self.policy, self.get_policy)
