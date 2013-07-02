"""
Test cron scheduler policies are executed via change, change percent
and desired caapacity
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep


class CronStyleSchedulerTests(AutoscaleFixture):

    """
    Verify cron style scheduler policy executes for all
    policy change types
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0 and cooldown=0
        """
        super(AutoscaleFixture, self).setUp()
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            lc_name="scheduled",
            gc_cooldown=0)
        self.group = create_group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def tearDown(self):
        """
        Scaling group deleted by the Autoscale fixture's teardown
        """
        super(AutoscaleFixture, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_cron_style_change_policy_up_down(self):
        """
        Create an cron style schedule via change to scale up and then scale down
        with 0 cooldown
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * 1-5')
        sleep(11)
        self.verify_group_state(self.group.id, self.sp_change)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_change=-self.sp_change,
            schedule_cron='* * * * 1-5')
        sleep(11)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_cron_style_change_percent_policy_up_down(self):
        """
        Create an cron style schedule via change percent to scale up and then scale down
        with 0 cooldown
        """
        pass

    def test_system_cron_style_desired_capacity_policy_up_down(self):
        """
        Create an at style schedule via change percent to scale up and then scale down
        with 0 cooldown
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=1,
            schedule_cron='* * * * 1-5')
        sleep(11)
        self.verify_group_state(self.group.id, self.sp_change)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=0,
            schedule_cron='* * * * 1-5')
        sleep(11)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_cron_style_policy_cooldown(self):
        """
        Create cron style scheduler via change and cooldown>0 to repeat execution before
        and after the cooldown expires
        """
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=20,
            sp_change=self.sp_change,
            schedule_cron='* * * * * *')
        sleep(11)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=cron_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 403)
        self.verify_group_state(self.group.id, self.sp_change)
        sleep(20)
        self.verify_group_state(self.group.id, self.sp_change*2)
