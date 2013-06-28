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

    # def test_schedule_cron_style_policy_invalid_cron(self):
    #     """
    #     Creating a scaling policy of type schedule with invalid cron results
    #     in a 400.
    #     """
    #     pass

    # def test_schedule_cron_style_policy_blank(self):
    #     """
    #     Creating a scaling policy of type schedule with (cron style) blank cron
    #     results in a 400.
    #     """
    #     args = {'cron': ''}
    #     create_schedule_at_style_response = self.autoscale_client.create_policy(
    #         group_id=self.group.id,
    #         name=self.sp_name, cooldown=self.sp_cooldown,
    #         change=self.sp_change, policy_type='schedule', args=args)
    #     self.assertEquals(create_schedule_at_style_response.status_code, 400,
    #                       msg='Create schedule scaling policy passed given an invalid date'
    #                       ' with {0} for group {1}'
    #                       .format(create_schedule_at_style_response.status_code, self.group.id))

    # def test_schedule_cron_style_policy_as_whitespace(self):
    #     """
    #     Creating a scaling policy of type schedule with (cron style) as whitespace
    #     results in a 400.
    #     """
    #     args = {'cron': '  '}
    #     create_schedule_at_style_response = self.autoscale_client.create_policy(
    #         group_id=self.group.id,
    #         name=self.sp_name, cooldown=self.sp_cooldown,
    #         change=self.sp_change, policy_type='schedule', args=args)
    #     self.assertEquals(create_schedule_at_style_response.status_code, 400,
    #                       msg='Create schedule scaling policy passed given an invalid date'
    #                       ' with {0} for group {1}'
    #                       .format(create_schedule_at_style_response.status_code, self.group.id))

    # def test_schedule_cron_style_policy_with_date(self):
    #     """
    #     Creating a scaling policy of type schedule via cron style but time as value
    #     results in a 400.
    #     """
    #     schedule_value = self.autoscale_behaviors.get_time_in_utc(60)
    #     schedule_policy_cron_style = self.autoscale_behaviors.create_schedule_policy_given(
    #         group_id=self.group.id,
    #         sp_change=self.sp_change,
    #         schedule_cron=schedule_value)
    #     self.assertEquals(schedule_policy_cron_style['status_code'], 400,
    #                       msg='Create schedule scaling cron style policy with time as value passed {0}'
    #                       ' for group {1}'
    #                      .format(schedule_policy_cron_style['status_code'], self.group.id))
