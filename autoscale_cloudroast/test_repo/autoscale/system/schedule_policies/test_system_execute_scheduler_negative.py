"""
Test negative scenarios for execution of at style and
cron style scheduler policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
import unittest


class ExecuteNegativeSchedulerPolicy(AutoscaleFixture):

    """
    Verify update scheduler policy
    """

    # def test_system_execute_at_style_scale_up_when_min_maxentities_are_met(self):
    #     """
    #     An at style scheduler policy's execution to scale up will fails with 403,
    #     if the maxentities on the group are already met
    #     """
    #     group = self._create_group(minentities=self.gc_min_entities,
    #                                maxentities=self.gc_min_entities, cooldown=0)
    #     self.create_default_at_style_policy_wait_for_execution(group.id)
    #     self.verify_group_state(group.id, self.gc_min_entities)
    #     self.create_default_at_style_policy_wait_for_execution(
    #         group.id, scale_down=True)
    #     self.verify_group_state(group.id, self.gc_min_entities)

    @unittest.skip('Cron not implemented yet')
    def test_system_execute_cron_style_scale_up_when_min_maxentities_are_met(self):
        """
        A cron style scheduler policy's execution to scale up will fails with 403,
        if the maxentities on the hroup are already met
        """
        group = self._create_group(
            0, self.gc_min_entities, self.gc_min_entities)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        sleep(self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)
        sleep(self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)

    def test_system_at_cron_style_execution_after_delete(self):
        """
        Create an at style and cron scheduler policy and delete them.
        Verify they do not trigger after they have been deleted.
        """
        group = self._create_group()
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(10))
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        self.autoscale_client.delete_scaling_policy(group.id, at_style_policy['id'])
        self.autoscale_client.delete_scaling_policy(group.id, cron_style_policy['id'])
        sleep(2*self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)

    def test_system_scheduler_down(self):
        """
        Create aat style and cron style schedule (every n seconds)and
        stop the scheduler until events accumulate in scaling schedule.
        Start scheduler and ensure all policies are executed
        """
        pass

    def test_system_scheduler_batch(self):
        """
        Create more policies than specified in batch and verify all of
        them are executed eventually
        """
        pass

    def test_create_multiple_scheduler_policies_to_execute_simaltaneously(self):
        """
        Create multiple scheduler policies such that all of them execute at the
        same time (within the scheduler interval)
        """
        pass

    def _create_group(self, minentities=None, maxentities=None, cooldown=None):
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=cooldown,
            gc_min_entities=minentities,
            gc_max_entities=maxentities)
        group = create_group_response.entity
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group
