"""
Test to delete the scheduler policy and verify.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class DeleteSchedulerPolicy(ScalingGroupFixture):

    """
    Verify delete scheduler policy
    """

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        on the scaling group with 0 minentities
        """
        super(DeleteSchedulerPolicy, self).setUp()
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

    def test_delete_at_style_scheduler(self):
        """
        Verify deleting the scheduler policy via at style,
        for response code 204, headers.
        """
        delete_at_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'])
        self.assertEquals(delete_at_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(delete_at_style_policy.status_code, self.group.id))
        self.assertTrue(delete_at_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(delete_at_style_policy.headers)
        self.assertTrue(self.at_style_policy['id'] not in self._policy_list_for_group(self.group.id))
        self.assertTrue(self.cron_style_policy['id'] in self._policy_list_for_group(self.group.id))

    def test_delete_cron_style_scheduler(self):
        """
        Verify deleting the scheduler policy via cron style,
        for response code 204, headers.
        """
        delete_at_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'])
        self.assertEquals(delete_at_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(delete_at_style_policy.status_code, self.group.id))
        self.assertTrue(delete_at_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(delete_at_style_policy.headers)
        self.assertTrue(self.at_style_policy['id'] in self._policy_list_for_group(self.group.id))
        self.assertTrue(self.cron_style_policy['id'] not in self._policy_list_for_group(self.group.id))

    def _policy_list_for_group(self, group_id):
        """
        Lists the policies in a group and returns the policy id list
        """
        list_policies_resp = self.autoscale_client.list_policies(group_id)
        return [each_policy.id for each_policy in list_policies_resp.entity]
