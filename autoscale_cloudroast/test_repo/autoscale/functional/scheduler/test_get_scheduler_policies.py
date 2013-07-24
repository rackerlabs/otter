"""
Test get scheduler policies (at and cron style).
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class GetSchedulerScalingPolicy(ScalingGroupFixture):

    """
    Verify get scheduler policies
    """

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        on the scaling group with 0 minentities
        """
        super(GetSchedulerScalingPolicy, self).setUp()
        self.at_value = self.autoscale_behaviors.get_time_in_utc(600)
        self.cron_value = '0 */10 * * *'
        self.at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id, sp_name='hahaha',
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

    def test_get_at_style_scaling_policy(self):
        """
        Verify get at style schedule policy's response code 200, headers and data
        """
        get_at_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.at_style_policy['id'])
        self.assertEquals(get_at_style_policy_response.status_code, 200,
                          msg='Get scaling policy (at style) failed with {0} for group {1}'
                          .format(get_at_style_policy_response.status_code,
                                  self.group.id))
        self.assertTrue(get_at_style_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(get_at_style_policy_response.headers)
        self.assert_get_policy(self.at_style_policy,
                               get_at_style_policy_response.entity,
                               args='at_style')

    def test_get_cron_style_scaling_policy(self):
        """
        Verify get cron style schedule policy's response code 200, headers and data
        """
        get_cron_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.cron_style_policy['id'])
        self.assertEquals(get_cron_style_policy_response.status_code, 200,
                          msg='Get scaling policy (cron style) failed with {0} for group {1}'
                          .format(get_cron_style_policy_response.status_code,
                                  self.group.id))
        self.assertTrue(get_cron_style_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(get_cron_style_policy_response.headers)
        self.assert_get_policy(self.cron_style_policy,
                               get_cron_style_policy_response.entity,
                               args='cron_style')

    def test_get_scheduler_cron_style_policy_after_deletion(self):
        """
        Negative Test: Get scheduler policy with cron style after policy is deleted
        fails with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        get_cron_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.cron_style_policy['id'])
        self.assertEquals(get_cron_style_policy_response.status_code, 404,
                          msg='get deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              get_cron_style_policy_response.status_code, self.group.id,
                              self.cron_style_policy['id']))

    def test_get_scheduler_at_style_policy_after_deletion(self):
        """
        Negative Test: Get scheduler policy with cron style after policy is deleted
        fails with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        get_at_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.at_style_policy['id'])
        self.assertEquals(get_at_style_policy_response.status_code, 404,
                          msg='get deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              get_at_style_policy_response.status_code, self.group.id,
                              self.at_style_policy['id']))
