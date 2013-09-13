"""
Test to delete and verify a cloud monitoring policy
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class DeleteMaasScalingPolicy(ScalingGroupFixture):

    """
    Verify delete cloud monitoring policy
    """

    def setUp(self):
        """
        Create a monitoring scaling policy
        """
        super(DeleteMaasScalingPolicy, self).setUp()
        self.policy = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id,
            check_type='remote.http')

    def test_delete_monitoring_policy(self):
        """
        Delete the monitoring policy and verify the response code and headers
        """
        delete_policy_response = self.autoscale_client.delete_scaling_policy(
            self.group.id,
            self.policy['id'])
        self.assertEqual(delete_policy_response.status_code, 204,
                         msg=('Delete monitoring policy was unsuccessful and resulted in {0}'
                              'for group {1}').format(delete_policy_response.status_code,
                                                      self.group.id))
        self.validate_headers(delete_policy_response['headers'])
