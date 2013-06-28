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
        Creates a scaling group with scheduler policy with type change
        """
        super(DeleteSchedulerPolicy, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(DeleteSchedulerPolicy, cls).tearDownClass()

    def test_delete_policy_schedule_at_style(self):
        """
        Verify the delete scheduler policy via at style,
        for response code 204, headers.
        To Do : verify scaling_schedule, in the database
        """
        policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change)
        delete_at_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=policy_at_style['id'])
        self.assertEquals(delete_at_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(delete_at_style_policy.status_code, self.group.id))
        self.assertTrue(delete_at_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(delete_at_style_policy.headers)

    def test_delete_policy_schedule_cron_style(self):
        """
        Verify the delete scheduler policy via cron style,
        for response code 204, headers.
        To Do : verify scaling_schedule, in the database
        """
        schedule_value = '0 */6 * * *'
        policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=schedule_value)
        delete_at_style_policy = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=policy_cron_style['id'])
        self.assertEquals(delete_at_style_policy.status_code, 204,
                          msg='Delete scheduler policy (at style) failed with {0}'
                          'for group {1}'
                          .format(delete_at_style_policy.status_code, self.group.id))
        self.assertTrue(delete_at_style_policy.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(delete_at_style_policy.headers)
