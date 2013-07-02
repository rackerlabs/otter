"""
Test at style scheduler policies are executed via change,
change percent and desired caapacity
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep


class AtStyleSchedulerTests(AutoscaleFixture):

    """
    Verify at style scheduler policy executes for all policy change types
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

    def test_system_at_style_to_execute_using_utc_time_now(self):
        """
        Create an at style scheduler via change and date as utc.now, should trigger
        the policy execution when created.
        """
        self.create_default_at_style_policy_wait_for_execution(self.group.id, 0)
        self.verify_group_state(
            self.group.id, self.sp_change)

    def test_system_at_style_change_policy_up_down(self):
        """
        Create an at style schedule via change to scale up and then scale down
        with 0 cooldown
        """
        self.create_default_at_style_policy_wait_for_execution(self.group.id, 10)
        self.verify_group_state(self.group.id, self.sp_change)
        self.create_default_at_style_policy_wait_for_execution(self.group.id, 20,
                                                               scale_down=True)
        self.verify_group_state(
            self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_at_style_desired_capacity_policy_up_down(self):
        """
        Create an at style schedule via change percent to scale up and then scale down
        with 0 cooldown
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=1,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(10))
        sleep(20)
        self.verify_group_state(self.group.id, 1)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=0,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(20))
        sleep(30)
        self.verify_group_state(
            self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_at_style_execute_before_cooldown(self):
        """
        Create 2 at style scheduler via change and cooldown>0 to execute before
        the cooldown expires
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=600,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(5))
        sleep(5 + 11)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=at_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 403)
        self.verify_group_state(self.group.id, self.sp_change)

    def test_system_at_style_execute_after_cooldown(self):
        """
        Create 2 at style scheduler via change and cooldown>0 to execute after
        the cooldown expires
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=10,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(5))
        sleep(5 + 10 + 11)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=at_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 202)
        self.verify_group_state(self.group.id, self.sp_change * 2)
