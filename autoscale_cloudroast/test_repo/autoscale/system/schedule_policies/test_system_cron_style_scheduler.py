"""
Test cron scheduler policies are executed via change, change percent
and desired caapacity
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
import unittest


@unittest.skip('cron not implemented yet')
class CronStyleSchedulerTests(AutoscaleFixture):

    """
    Verify cron style scheduler policy executes for all
    policy change types
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0 and cooldown=0
        """
        super(CronStyleSchedulerTests, self).setUp()
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
        super(CronStyleSchedulerTests, self).tearDown()
        self.empty_scaling_group(self.group)

    def test_system_cron_style_change_policy_up_down(self):
        """
        Create a cron style schedule policy via change to scale up by 2, followed by
        a cron style schedule policy to scale down by -2, each policy with 0 cooldown.
        The total servers after execution of both policies is the minentities with
        which the group was created.
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * 1-5')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.sp_change)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_change=-self.sp_change,
            schedule_cron='* * * * 1-5')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_cron_style_desired_capacity_policy_up_down(self):
        """
        Create a cron style schedule policy via desired capacity to scale up by 1,
        followed by a cron style schedule policy to scale down to 0,
        each policy with 0 cooldown. The total servers after execution of both
        policies is 0.
        """
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=1,
            schedule_cron='* * * * 1-5')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.sp_change)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=0,
            sp_desired_capacity=0,
            schedule_cron='* * * * 1-5')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)

    def test_system_cron_style_policy_cooldown(self):
        """
        Create a cron style scheduler policy via change to scale up with cooldown>0,
        wait for it to execute. Re-execute the policy manually before the
        cooldown results in 403. Then wait for the cron style policy to re-trigger
        after the cooldown period and verify the total active servers on the group
        are equal to be 2 times the change value specifies in scale up policy
        """
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_cooldown=20,
            sp_change=self.sp_change,
            schedule_cron='* * * * * *')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.sp_change)
        execute_scheduled_policy = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=cron_style_policy['id'])
        self.assertEquals(execute_scheduled_policy.status_code, 403)
        self.verify_group_state(self.group.id, self.sp_change)
        sleep(self.scheduler_interval * 2)
        self.verify_group_state(self.group.id, self.sp_change * 2)
