"""
Test list scheduler policies (at and cron style).
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class ListSchedulerScalingPolicy(ScalingGroupPolicyFixture):

    """
    Verify list scheduler policies
    """

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        on a scaling group with an existing webhook type policy
        """
        super(ListSchedulerScalingPolicy, self).setUp()
        self.at_value = self.autoscale_behaviors.get_time_in_utc(600)
        self.cron_value = '0 */10 * * *'
        self.at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=self.at_value)
        self.assertEquals(self.at_style_policy['status_code'], 201,
                          msg='Create schedule policy (at style) failed with {0} for group {1}'
                          .format(self.at_style_policy['status_code'], self.group.id))
        self.cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=self.cron_value)
        self.assertEquals(self.cron_style_policy['status_code'], 201,
                          msg='Create schedule policy (cron style) failed with {0} for group {1}'
                          .format(self.cron_style_policy['status_code'], self.group.id))

    def test_list_scheduler_policies(self):
        """
        Verify list scheduler policies' response code 200, headers and data
        """
        list_policies_resp = self.autoscale_client.list_policies(self.group.id)
        self.assertEquals(list_policies_resp.status_code, 200,
                          msg='List  for a policy failed with {0}'
                          .format(list_policies_resp.status_code))
        self.validate_headers(list_policies_resp.headers)
        policy_id_list = [each_policy.id for each_policy in list_policies_resp.entity]
        self.assertTrue(self.at_style_policy['id'] in policy_id_list)
        self.assertTrue(self.cron_style_policy['id'] in policy_id_list)
        self.assertTrue(self.policy['id'] in policy_id_list)
