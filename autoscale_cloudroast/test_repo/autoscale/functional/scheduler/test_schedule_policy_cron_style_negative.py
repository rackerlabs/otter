"""
Test for negative scenarios to a scaling policy of type schedule with cron style.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScheduleScalingPolicyCronStyleNegative(AutoscaleFixture):

    """
    Negative scenarios for scaling policy of type schedule with cron style.
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(ScheduleScalingPolicyCronStyleNegative, cls).setUpClass()
        cls.scheduler_type = 'schedule'

    def setUp(self):
        """
        Create a scaling group with minentities=0
        """
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_min(
        )
        self.group = self.create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Scaling group deleted by the Autoscale fixture's teardown
        """
        pass

    def test_schedule_cron_style_policy_invalid_cron(self):
        """
        Creating a scaling policy of type schedule with invalid cron results
        in a 400.
        ** '* * * * * *' -> 201 **
        """
        schedule_value_list = ['* * * *', '* * * * * *', '* * * * * * * *', '*'
                               '12345', 'dfsdfdf', '0-59 0-23 1-31 1-12 0-6', '- - - - -']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_blank(self):
        """
        Creating a scaling policy of type schedule with (cron style) blank cron
        results in a 400.
        """
        args = {'cron': ''}
        create_schedule_at_style_response = self.autoscale_client.create_policy(
            group_id=self.group.id,
            name=self.sp_name, cooldown=self.sp_cooldown,
            change=self.sp_change, policy_type='schedule', args=args)
        self.assertEquals(create_schedule_at_style_response.status_code, 400,
                          msg='Create schedule scaling policy passed given an invalid date'
                          ' with {0} for group {1}'
                          .format(create_schedule_at_style_response.status_code, self.group.id))

    def test_schedule_cron_style_policy_as_whitespace(self):
        """
        Creating a scaling policy of type schedule with (cron style) as whitespace
        results in a 400.
        """
        args = {'cron': '  '}
        create_schedule_at_style_response = self.autoscale_client.create_policy(
            group_id=self.group.id,
            name=self.sp_name, cooldown=self.sp_cooldown,
            change=self.sp_change, policy_type='schedule', args=args)
        self.assertEquals(create_schedule_at_style_response.status_code, 400,
                          msg='Create schedule scaling policy passed given an invalid date'
                          ' with {0} for group {1}'
                          .format(create_schedule_at_style_response.status_code, self.group.id))

    def test_schedule_cron_style_policy_with_date(self):
        """
        Creating a scaling policy of type schedule via cron style but time as value
        results in a 400.
        """
        schedule_value = self.autoscale_behaviors.get_time_in_utc(60)
        schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=schedule_value)
        self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                          msg='Create schedule scaling cron style policy with time as value passed {0}'
                          ' for group {1}'
                          .format(schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_special_cron_keywords(self):
        """
        Creating a scaling policy of type schedule with special cron keywords
        """
        schedule_value_list = ['@yearly', '@daily', '@hourly', '@reboot', '@weekly', '@monthly']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule policy with invalid cron style results in{0}'
                              ' for group {1}'
                              .format(schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_with_invalid_cron_minute(self):
        """
        Creating a scaling policy of type schedule via cron style with invalid minute value in
        cron results in a 400.
        ** '-090 * * * *' -> 500 **
        """
        schedule_value_list = ['60 * * * *', '-090 * * * *',
                               '2- * * * *', '6-0 * * * *',
                               '-9 * * * *', '$ * * * *']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_with_invalid_cron_hour(self):
        """
        Creating a scaling policy of type schedule via cron style with invalid hour value in
        cron results in a 400.
        ** '* -089 * * *' -> 500 **
        """
        schedule_value_list = ['* 24 * * *', '* -089 * * *',
                               '* 2- * * *', '* 6-0 * * *',
                               '* -9 * * *', '* $ * * *']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_with_invalid_cron_day(self):
        """
        Creating a scaling policy of type schedule via cron style with invalid day value in
        cron results in a 400.
        ** '* * -32 * *' -> 500, '* * 0 * *' -> 201 **
        """
        schedule_value_list = ['* * 0 * *', '* * -32 * *',
                               '* * 0-0 * *', '* * 2- * *',
                               '* * 6-0 * *', '* * -9 * *', '* * $ * *']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_with_invalid_cron_month(self):
        """
        Creating a scaling policy of type schedule via cron style with invalid month value in
        cron results in a 400.
        ** '* * * -30 *' -> 500 **
        """
        schedule_value_list = ['* * * -30 *', '* * * 13 *',
                               '* * * 0-0 *', '* * * 2- *',
                               '* * * 6-0 *', '* * * -9 *', '* * * $ *']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_schedule_cron_style_policy_with_invalid_cron_week(self):
        """
        Creating a scaling policy of type schedule via cron style with invalid week value in
        cron results in a 400.
        ** fails with 201 for '* * * * 7' **
        """
        schedule_value_list = ['* * * * 7', '* * * * 0-0',
                               '* * * * 2-', '* * * * 6-0',
                               '* * * * -9', '* * * * $']
        for each_schedule_value in schedule_value_list:
            schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
                group_id=self.group.id,
                sp_change=self.sp_change,
                schedule_cron=each_schedule_value)
            self.assertEquals(schedule_policy_cron_style['status_code'], 400,
                              msg='Create schedule cron style policy with {0} results in {1}'
                              ' for group {2}'
                              .format(each_schedule_value,
                                      schedule_policy_cron_style['status_code'], self.group.id))

    def test_scaling_policy_cooldown_lessthan_zero(self):
        """
        Negative Test: Scheduler policy should not get created with
        cooldown less than zero.
        """
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name=self.sp_name,
                                                                cooldown='-00.01',
                                                                change=self.sp_change,
                                                                policy_type=self.scheduler_type,
                                                                args={'at': '2013-12-23T11:11:11Z'})
        self.assertEquals(error_create_resp.status_code, 400,
                          msg='Create scaling policy succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))

    def test_scaling_policy_change_lessthan_zero(self):
        """
        Negative Test: Scheduler policy should not get created with change less than zero
        """
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name=self.sp_name,
                                                                cooldown=self.sp_cooldown,
                                                                change=-00.01,
                                                                policy_type=self.scheduler_type,
                                                                args={'cron': '* * * * *'})
        self.assertEquals(error_create_resp.status_code, 400,
                          msg='Create scaling policy succeeded with invalid request: {0}'
                          .format(error_create_resp.status_code))

    def test_schedule_cron_style_policy_with_webhook(self):
        """
        Creating a webhook on a scaling policy of type schedule with (at style)
        results in a 400.
        """
        schedule_value = '* * * * *'
        schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=schedule_value)
        self.assertEquals(schedule_policy_cron_style['status_code'], 201,
                          msg='Create scheduler at style policy with failed'
                          ' with {0} for group {1}'
                          .format(schedule_policy_cron_style['status_code'], self.group.id))
        create_webhook_response = self.autoscale_client.create_webhook(
            group_id=self.group.id,
            policy_id=schedule_policy_cron_style['id'],
            name=self.wb_name)
        self.assertEquals(create_webhook_response.status_code, 400,
                          msg='Create webhook on a scheduler cron style policy failed'
                          ' with {0} for group {1}'
                          .format(create_webhook_response.status_code, self.group.id))
