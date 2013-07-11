"""
Test scenarios for scaling policy of type schedule with cron style.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest


class ScheduleScalingPolicyCronAndAtStyle(AutoscaleFixture):

    """
    Scenarios for scaling policy of type schedule with cron style.
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0
        """
        super(ScheduleScalingPolicyCronAndAtStyle, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_min()
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def test_schedule_cron_style_policy_valid_cron(self):
        """
        Creating a scaling policy of type schedule with different valid crons results
        in a 201.
        * To Do : validate 'trigger' in scaling_schedule, in the database *
        """
        schedule_value_list = [
            '* * * * *', '0-59 0-23 1-31 1-12 0-6', '00 9,16 * * *',
            '00 02-11 * * *', '00 09-18 * * 1-5', '0 0 0 0 0', '* * * * * *']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 201,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))
            self.assertEquals(
                schedule_policy_cron_style['schedule_type'], 'cron',
                msg="Scaling policy's schedule type does not match")
            self.assertEquals(
                schedule_policy_cron_style[
                    'schedule_value'], each_schedule_value,
                msg="Scaling policy's schedule value does not match")

    @unittest.skip('AUTO-434')
    def test_schedule_at_style_policy_without_seconds(self):
        """
        Creating a scaling policy of type schedule with (at style) without seconds
        results in a 201.
        ** fails with 400, AUTO-434**
        """
        schedule_value_list = [self.autoscale_behaviors.get_time_in_utc(3155760000),
                               '2013-12-05T03:12Z']
        for each_schedule_value in schedule_value_list:
            schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_at=each_schedule_value)
            self.assertEquals(schedule_policy_at_style['status_code'], 201,
                              msg='Create schedule scaling at style policy without seconds results'
                              'in {0} for group {1}'
                              .format(schedule_policy_at_style['status_code'], self.group.id))
            self.assertEquals(
                schedule_policy_at_style['schedule_type'], 'at',
                msg="Scaling policy's schedule type does not match")
            self.assertEquals(
                schedule_policy_at_style[
                    'schedule_value'], each_schedule_value,
                msg="Scaling policy's schedule value does not match")
