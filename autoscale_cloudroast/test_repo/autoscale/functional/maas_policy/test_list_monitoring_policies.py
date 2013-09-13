"""
Test to list and verify a cloud monitoring policies
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class ListMaasScalingPolicy(ScalingGroupFixture):

    """
    Verify delete cloud monitoring policy
    """

    def setUp(self):
        """
        Create multiple monitoring scaling policies
        """
        super(ListMaasScalingPolicy, self).setUp()
        self.policy1 = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id)
        self.policy2 = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id)
        self.policy3 = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id)

    def test_list_monitoring_policy(self):
        """
        List the monitoring policy and verify the response code, response and headers
        """
        policy_id_list = []
        list_policies_resp = self.autoscale_client.list_policies(self.group.id)
        self.assertEquals(list_policies_resp.status_code, 200,
                          msg='List monitoring policies failed with {0} for group'
                          ' {1}'.format(list_policies_resp.status_code, self.group.id))
        self.validate_headers(list_policies_resp.headers)
        policy_id_list = [policy.id for policy in list_policies_resp.entity]
        self.assertTrue(self.policy1['policy_id'] in policy_id_list)
        self.assertTrue(self.policy2['policy_id'] in policy_id_list)
        self.assertTrue(self.policy3['policy_id'] in policy_id_list)
