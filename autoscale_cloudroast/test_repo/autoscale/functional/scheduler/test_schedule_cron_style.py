"""
Test scenarios for scaling policy of type schedule with cron style.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ScheduleScalingPolicyCronStyleNegative(AutoscaleFixture):

    """
    Scenarios for scaling policy of type schedule with cron style.
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

    def test_schedule_cron_style_policy_invalid_cron(self):
        """
        Creating a scaling policy of type schedule with different valid crons results
        in a 201.
        * To Do : validate 'trigger' in scaling_schedule, in the database *
        """
        schedule_value_list = [
            '* * * * *', '0-59 0-23 1-31 1-12 0-6', '00 9,16 * * *',
            '00 02-11 * * *', '00 09-18 * * 1-5', '0 0 0 0 0']
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
