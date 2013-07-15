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

    def test_system_execute_at_style_scale_up_when_min_maxentities_are_met(self):
        """
        When min and max entities are already met on a scaling group, an at style
        scheduler policy to scale up or scale down will not be triggered.
        """
        group = self._create_group(minentities=self.gc_min_entities,
                                   maxentities=self.gc_min_entities, cooldown=0)
        self.create_default_at_style_policy_wait_for_execution(group.id)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        self.create_default_at_style_policy_wait_for_execution(
            group.id, scale_down=True)
        self.verify_group_state(group.id, group.groupConfiguration.maxEntities)

    @unittest.skip('Cron not implemented yet')
    def test_system_execute_cron_style_scale_up_when_min_maxentities_are_met(self):
        """
        When min and max entities are already met on a scaling group, an cron style
        scheduler policy to scale up or scale down will not be triggered.
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

    @unittest.skip('Cron not implemented yet')
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
        self.autoscale_client.delete_scaling_policy(
            group.id, at_style_policy['id'])
        self.autoscale_client.delete_scaling_policy(
            group.id, cron_style_policy['id'])
        sleep(2 * self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)

    def test_system_scheduler_down(self):
        """
        Stop the scheduler. Create at style and cron style schedule (every n seconds)and
        verify events accumulate in scaling schedule table.
        Start scheduler and ensure all policies are executed.
        """
        pass

    @unittest.skip('AUTO-442')
    def test_system_scheduler_batch(self):
        """
        Create more number of policies than specified in scheduler batch size and verify all
        of them are executed in the batch size specified.
        (currently blocked by AUTO-443)
        """
        at_style_list = []
        for each in (range(1, self.scheduler_batch + 2)):
            each = dict(
                args=dict(at=self.autoscale_behaviors.get_time_in_utc(0)),
                cooldown=0, type='schedule', name='multi_at_style{0}'.format(each), change=1)
            at_style_list.append(each)
        create_group_reponse = self.autoscale_behaviors.create_scaling_group_given(
            lc_name='multi_scheduling', gc_cooldown=0,
            sp_list=at_style_list)
        sleep(self.scheduler_interval + self.scheduler_interval / 2)
        self.verify_group_state(create_group_reponse.entity.id, self.scheduler_batch + 2)

    @unittest.skip('AUTO-442')
    def test_create_multiple_scheduler_policies_to_execute_simaltaneously(self):
        """
        Create multiple scheduler policies within the same group such that all of them are
        triggered by the scheduler, at the same time, and ensure all the policies
        are executed successfully.
        ** fails due to the locks presumably, see gist**
        """
        at_style_list = []
        for each in (1, 2, 3):
            each = dict(
                args=dict(at=self.autoscale_behaviors.get_time_in_utc(0)),
                cooldown=0, type='schedule', name='multi_at_style', change=each)
            at_style_list.append(each)
        create_group_reponse = self.autoscale_behaviors.create_scaling_group_given(
            lc_name='multi_scheduling', gc_cooldown=0,
            sp_list=at_style_list)
        group = create_group_reponse.entity
        sleep(self.scheduler_interval)
        self.verify_group_state(group.id, 1 + 2 + 3)

    def _create_group(self, minentities=None, maxentities=None, cooldown=None):
        """
        Create a group, add group to resource pool and return the group
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=cooldown,
            gc_min_entities=minentities,
            gc_max_entities=maxentities)
        group = create_group_response.entity
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group
