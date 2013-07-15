"""
Test to delete the policy and verify.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class DeleteScalingPolicy(ScalingGroupPolicyFixture):
    """
    Verify delete policy
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with policy with type change
        """
        super(DeleteScalingPolicy, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(DeleteScalingPolicy, cls).tearDownClass()

    def test_delete_scaling_policy(self):
        """
        Verify the delete policy call for response code 204, headers.
        """
        delete_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'])
        self.assertEquals(delete_policy.status_code, 204,
                          msg='Delete scaling policy failed with {0}'
                          .format(delete_policy.status_code))
        self.validate_headers(delete_policy.headers)
