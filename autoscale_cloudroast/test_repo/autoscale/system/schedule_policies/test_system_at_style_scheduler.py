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
        super(AtStyleSchedulerTests, self).setUp()
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
        super(AtStyleSchedulerTests, self).tearDown()
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
        Create an at style schedule policy via change to scale up by 2, followed by an
        at style schedule policy to scale down by -2, each policy with 0 cooldown.
        The total servers after execution of both policies is the minentities with
        which the group was created.
        """
        self.create_default_at_style_policy_wait_for_execution(self.group.id, 10)
        self.verify_group_state(self.group.id, self.sp_change)
        self.create_default_at_style_policy_wait_for_execution(self.group.id, 20,
                                                               scale_down=True)
        self.verify_group_state(
            self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_at_style_desired_capacity_policy_up_down(self):
        """
        Create an at style schedule policy via desired capacity to scale up by 1,
        followed by an at style schedule policy to scale down to 0,
        each policy with 0 cooldown. The total servers after execution of both
        is 0.
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=1,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(10))
        sleep(10 + self.scheduler_interval)
        self.verify_group_state(self.group.id, 1)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=0,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(20))
        sleep(20 + self.scheduler_interval)
        self.verify_group_state(self.group.id, 0)

    def test_system_at_style_execute_before_cooldown(self):
        """
        Create an at style scheduler policy via change to scale up with cooldown>0,
        and wait for it to execute. Re-execute the policy manually before the
        cooldown results in 403
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=600,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(5))
        sleep(5 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=at_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 403)
        self.verify_group_state(self.group.id, self.sp_change)

    def test_system_at_style_execute_after_cooldown(self):
        """
        Create an at style scheduler policy via change to scale up with cooldown>0,
        and wait for it to execute. Re-executing the policy manually after the
        cooldown period, results in total active servers on the group to be 2 times
        the change value specifies in scale up policy
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=10,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(5))
        sleep(5 + 10 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=at_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 202)
        self.verify_group_state(self.group.id, self.sp_change * 2)
