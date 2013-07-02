"""
Test to delete the scheduler policy and verify.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class DeleteSchedulerPolicy(ScalingGroupFixture):

    """
    Verify delete scheduler policy
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group with minentities=0
        """
        super(DeleteSchedulerPolicy, cls).setUpClass()

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        """
        self.at_value = self.autoscale_behaviors.get_time_in_utc(600)
        self.cron_value = '0 */10 * * *'
        self.at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=self.at_value)
        self.assertEquals(self.at_style_policy['status_code'], 201,
                          msg='Create schedule policy (at style) failed with {0} for group {1}'
                          .format(self.at_style_policy['status_code'], self.group.id))
        self.delete_at_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'])
        self.assertEquals(self.delete_at_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(self.delete_at_style_policy.status_code, self.group.id))
        self.cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=self.cron_value)
        self.assertEquals(self.cron_style_policy['status_code'], 201,
                          msg='Create schedule policy (cron style) failed with {0} for group {1}'
                          .format(self.cron_style_policy['status_code'], self.group.id))
        self.delete_cron_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'])
        self.assertEquals(self.delete_cron_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(self.delete_cron_style_policy.status_code, self.group.id))

    def tearDown(self):
        """
        Scaling group deleted by the Autoscale fixture's teardown
        """
        pass

    def test_delete_policy_schedule_at_style_and_cron_style(self):
        """
        Verify the delete scheduler policy via at style and cron style,
        for response code 204, headers.
        """
        self.assertTrue(self.delete_at_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(self.delete_at_style_policy.headers)
        self.assertTrue(self.delete_cron_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(self.delete_cron_style_policy.headers)
