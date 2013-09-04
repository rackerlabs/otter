"""
Test to create and verify a schedule policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class CreateScheduleScalingPolicy(ScalingGroupFixture):

    """
    Verify create schedule policy.
    """

    def test_create_schedule_cron_style_scaling_policy(self):
        """
        Create a scaling policy of type schedule and via cron style,
        verify response code 201, headers and data.
        """
        schedule_type = 'cron'
        schedule_value = '0 */6 * * *'
        schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=schedule_value)
        self.assertEquals(schedule_policy_cron_style['status_code'], 201,
                          msg='Create schedule scaling policy failed with {0} for group {1}'
                          .format(schedule_policy_cron_style['status_code'], self.group.id))
        self.validate_headers(schedule_policy_cron_style['headers'])
        self.assertTrue(schedule_policy_cron_style['id'] is not None,
                        msg='Scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(schedule_policy_cron_style['links'] is not None,
                        msg="Newly created scaling policy's links are null for group "
                        '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_cron_style['cooldown'], self.sp_cooldown,
                          msg="scaling policy's cooldown time does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_cron_style['change'], self.sp_change,
                          msg="Scaling policy's change does not match  for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_cron_style['schedule_type'], schedule_type,
                          msg="Scaling policy's schedule type does not match  for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_cron_style['schedule_value'], schedule_value,
                          msg="Scaling policy's schedule value does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_cron_style['count'], 1,
                          msg='More scaling policies listed than created for group '
                          '{0}'.format(self.group.id))

    def test_create_schedule_at_style_scaling_policy(self):
        """
        Create a scaling policy of type schedule via at style,
        and verify response code 201, headers and data.
        """
        schedule_type = 'at'
        schedule_value = self.autoscale_behaviors.get_time_in_utc(60)
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 201,
                          msg='Create schedule scaling policy failed with {0} for group '
                          '{1}'.format(schedule_policy_at_style['status_code'], self.group.id))
        self.validate_headers(schedule_policy_at_style['headers'])
        self.assertTrue(schedule_policy_at_style['id'] is not None,
                        msg='Scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(schedule_policy_at_style['links'] is not None,
                        msg="Newly created scaling policy's links are null for group "
                        '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_at_style['cooldown'], self.sp_cooldown,
                          msg="scaling policy's cooldown time does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_at_style['change'], self.sp_change,
                          msg="Scaling policy's change does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_at_style['schedule_type'], schedule_type,
                          msg="Scaling policy's schedule type does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_at_style['schedule_value'], schedule_value,
                          msg="Scaling policy's schedule value does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(schedule_policy_at_style['count'], 1,
                          msg='More scaling policies listed than created for group '
                          '{0}'.format(self.group.id))
