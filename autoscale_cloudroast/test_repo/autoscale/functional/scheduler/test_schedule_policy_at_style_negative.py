"""
Test for negative scenarios to a scaling policy of type schedule.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest


class ScheduleScalingPolicyNegative(AutoscaleFixture):

    """
    Negative scenarios for scaling policy of type schedule.
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0
        """
        super(ScheduleScalingPolicyNegative, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_min()
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def test_at_style_to_execute_using_utc_time_now(self):
        """
        Create an at style scheduler via change and date as utc.now, should result in 400.
        """
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(0))
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with current time'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_different_date_format_1(self):
        """
        Creating a scaling policy of type schedule with (at style) with non iso8601 date
        format results in a 400.
        """
        schedule_value = '05-12-2013T03:12:09Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with a different date format'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_different_date_format_2(self):
        """
        Creating a scaling policy of type schedule with (at style) with non iso8601 date
        format results in a 400.
        """
        schedule_value = '2013/12/30T03:12:09Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with a different date format'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_no_z_in_date(self):
        """
        Creating a scaling policy of type schedule with (at style) with no Z in date
        format results in a 400.
        ** AUTO-405, fails with 201**
        """
        schedule_value = '2013-12-05T03:12:09'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with no Z in date'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_no_t_in_date(self):
        """
        Creating a scaling policy of type schedule with (at style) with no T in date
        format results in a 400.
        ** AUTO-405, fails with 201**
        """
        schedule_value = '2013-12-05 03:12:09Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with no T in date'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_no_z_or_t_in_date(self):
        """
        Creating a scaling policy of type schedule with (at style) with no Z or T in date
        format results in a 400.
        ** AUTO-405, fails with 201**
        """
        schedule_value = '2013-12-05 03:12:09'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule policy via at style with no Z or T in date'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_date_in_the_past(self):
        """
        Creating a scaling policy of type schedule with (at style) date in the past
        results in a 400.
        ** Auto 404, fails with 201 **
        """
        schedule_value = self.autoscale_behaviors.get_time_in_utc(-172800)
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with date in the past'
                          'results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_only_date(self):
        """
        Creating a scaling policy of type schedule with (at style) only date
        results in a 400.
        """
        schedule_value = '2013-06-05'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with only date results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_integers(self):
        """
        Creating a scaling policy of type schedule with at style date as integers
        results in a 400.
        """
        schedule_value = '031260'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with time as random'
                          'integers results in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_only_time(self):
        """
        Creating a scaling policy of type schedule with (at style) only time
        results in a 400.
        """
        schedule_value = '03:12:60'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with only time results'
                          'in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_blank_date(self):
        """
        Creating a scaling policy of type schedule with (at style) blank date
        results in a 400.
        """
        args = {'at': ''}
        create_schedule_at_style_response = self.autoscale_client.create_policy(
            group_id=self.group.id,
            name=self.sp_name, cooldown=self.sp_cooldown,
            change=self.sp_change, policy_type='schedule', args=args)
        self.assertEquals(create_schedule_at_style_response.status_code, 400,
                          msg='Create schedule policy passed given blank for date'
                          ' with {0} for group {1}'
                          .format(create_schedule_at_style_response.status_code, self.group.id))

    def test_schedule_at_style_policy_date_as_whitespace(self):
        """
        Creating a scaling policy of type schedule with (at style) date as whitespace
        results in a 400.
        """
        args = {'at': '  '}
        create_schedule_at_style_response = self.autoscale_client.create_policy(
            group_id=self.group.id,
            name=self.sp_name, cooldown=self.sp_cooldown,
            change=self.sp_change, policy_type='schedule', args=args)
        self.assertEquals(create_schedule_at_style_response.status_code, 400,
                          msg='Create schedule policy passed given whitespace as date'
                          ' with {0} for group {1} (at style)'
                          .format(create_schedule_at_style_response.status_code, self.group.id))

    def test_schedule_at_style_policy_with_cron_value(self):
        """
        Creating a scaling policy of type schedule via at style but at as value
        results in a 400.
        """
        schedule_value = '23 * * * *'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with cron as value passed'
                          ': {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_string_as_date(self):
        """
        Creating a scaling policy of type schedule with (at style) as string
        results in a 400.
        """
        schedule_value = '"uyytuy^&&^%&^"'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with string, results in'
                          '{0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_month_in_date(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid month in the date
        results in a 400.
        """
        schedule_value = '2013-13-05T03:12:00Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid month results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_year(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid year in the date
        results in a 400.
        """
        schedule_value = '0000-12-05T03:12:00Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid year results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_day(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid day in the date
        results in a 400.
        """
        schedule_value = '2013-12-33T03:12:00Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid day results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_hour(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid hour in the date
        results in a 400.
        """
        schedule_value = '2013-12-10T27:12:00Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid hour results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_minute(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid minute in the date
        results in a 400.
        """
        schedule_value = '2013-12-31T10:70:00Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid minute results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    def test_schedule_at_style_policy_with_invalid_second(self):
        """
        Creating a scaling policy of type schedule with (at style) with invalid second in the date
        results in a 400.
        """
        schedule_value = '2013-12-31T10:10:80Z'
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=schedule_value)
        self.assertEquals(schedule_policy_at_style['status_code'], 400,
                          msg='Create schedule scaling at style policy with invalid second results'
                          ' in {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))

    @unittest.skip('AUTO-418')
    def test_schedule_at_style_policy_with_webhook(self):
        """
        Creating a webhook on a scaling policy of type schedule with (at style)
        results in a 400.
        ** AUTO-418, fails with 201 for webhook creation **
        """
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change)
        self.assertEquals(schedule_policy_at_style['status_code'], 201,
                          msg='Create scheduler at style policy with failed'
                          ' with {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))
        create_webhook_response = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=schedule_policy_at_style['id'],
            name=self.wb_name)
        self.assertEquals(create_webhook_response.status_code, 400,
                          msg='Create webhook on a scheduler at style policy failed'
                          ' with {0} for group {1}'
                          .format(create_webhook_response.status_code, self.group.id))

    @unittest.skip('AUTO-418')
    def test_schedule_at_style_policy_execute(self):
        """
        Create scaling policy of type schedule with (at style) and execute it,
        results in a 400.
        ** AUTO-418, fails with 202 upon execution, and creates/deletes servers as
        per policy **
        """
        schedule_policy_at_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change)
        self.assertEquals(schedule_policy_at_style['status_code'], 201,
                          msg='Create scheduler at style policy with failed'
                          ' with {0} for group {1}'
                          .format(schedule_policy_at_style['status_code'], self.group.id))
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=schedule_policy_at_style['id'])
        self.assertEquals(execute_policy_response.status_code, 400,
                          msg='Able to execute scheduler policy via at style policy'
                          ' with {0} for group {1}'
                          .format(execute_policy_response.status_code, self.group.id))
