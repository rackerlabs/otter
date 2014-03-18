"""
Test negative scenarios for execution of at style and
cron style scheduler policies
"""

from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
from cafe.drivers.unittest.decorators import tags
from cloudcafe.common.tools.datagen import rand_name
import unittest


class ExecuteNegativeSchedulerPolicy(AutoscaleFixture):

    """
    Verify update scheduler policy
    """

    @tags(speed='slow')
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

    @tags(speed='slow')
    def test_system_execute_cron_style_scale_up_when_min_maxentities_are_met(self):
        """
        When min and max entities are already met on a scaling group, a cron style
        scheduler policy to scale up or scale down will not be triggered.
        """
        group = self._create_group(
            0, self.gc_min_entities, self.gc_min_entities)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=-self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)

    @unittest.skip("Skipping until CRON timing test issues are addressed")
    @tags(speed='slow')
    def test_system_cron_style_when_policy_cooldown_over_trigger_period(self):
        """
        When policy cooldown is set to be greater than a minute by few seconds for a
        cron style policy that is set to trigger every minute, that policy is
        executed every other time.
        """
        group = self._create_group(cooldown=0)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=65,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change * 2)

    @unittest.skip("Skipping until CRON timing test issues are addressed")
    @tags(speed='slow')
    def test_system_cron_style_when_group_cooldown_over_trigger_period(self):
        """
        When group cooldown is set to be greater than a minute by few seconds for a
        cron style policy that is set to trigger every minute, that policy is
        executed every other time.
        """
        group = self._create_group(cooldown=65)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change)
        sleep(70 + self.scheduler_interval)
        self.verify_group_state(group.id, self.sp_change * 2)

    @tags(speed='slow')
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
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, self.gc_min_entities)

    def test_system_scheduler_down(self):
        """
        Stop the scheduler. Create at style and cron style schedule (every n seconds)and
        verify events accumulate in scaling schedule table.
        Start scheduler and ensure all policies are executed.
        """
        pass

    @tags(speed='quick')
    def test_system_scheduler_batch(self):
        """
        Create more number of policies than specified in scheduler batch size and verify all
        of them are executed in the batch size specified.
        """
        lc_name = rand_name('scheduler_batch_size_check')
        at_style_policies_list = []
        size = 1
        at_style_time = self.autoscale_behaviors.get_time_in_utc(10)
        for policy in (range(self.scheduler_batch * size)):
            policy = {
                'args': {'at': at_style_time},
                'cooldown': 0,
                'type': 'schedule',
                'name': 'multi_at_style{0}'.format(policy),
                'change': 1}
            at_style_policies_list.append(policy)
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            lc_name=lc_name, gc_cooldown=0,
            sp_list=at_style_policies_list)
        group = create_group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        sleep(self.scheduler_interval * 2)
        self.check_for_expected_number_of_building_servers(group.id, self.scheduler_batch * size)
        self.verify_group_state(group.id, self.scheduler_batch * size)

    @tags(speed='slow')
    def test_create_multiple_scheduler_policies_to_execute_simaltaneously(self):
        """
        Create multiple scheduler policies within the same group such that all of them are
        triggered by the scheduler, at the same time, and ensure all the policies
        are executed successfully.
        """
        at_style_policies_list = []
        for policy in (1, 2, 3):
            policy = {
                'args': {'at': self.autoscale_behaviors.get_time_in_utc(1)},
                'cooldown': 0,
                'type': 'schedule',
                'name': 'multi_at_style{0}'.format(policy),
                'change': policy}
            at_style_policies_list.append(policy)
        create_group_reponse = self.autoscale_behaviors.create_scaling_group_given(
            lc_name='multi_scheduling', gc_cooldown=0,
            sp_list=at_style_policies_list)
        group = create_group_reponse.entity
        self.resources.add(group, self.empty_scaling_group)
        sleep(self.scheduler_interval)
        self.verify_group_state(group.id, 1 + 2 + 3)

    @tags(speed='quick')
    def test_system_update_at_and_cron_style_scheduler_policy_to_webhook_type(self):
        """
        Policy updation fails when a cron style scheduler /at style scheduler is updated to
        be of type webhook, with error 400
        """
        group = self._create_group()
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(600))
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        for each_policy in [at_style_policy['id'], cron_style_policy['id']]:
            upd_policy_response = self.autoscale_client.update_policy(
                group_id=group.id,
                policy_id=each_policy,
                name='upd_scheduler_to_webhook',
                cooldown=self.sp_cooldown,
                change=self.sp_change,
                policy_type='webhook')
            self.assertEquals(upd_policy_response.status_code, 400,
                              msg='Update scheduler policy to webhook policy type'
                              ' on the group {0} with response code {1}'.format(
                              group.id, upd_policy_response.status_code))

    def _create_group(self, minentities=None, maxentities=None, cooldown=None):
        """
        Create a group, add group to resource pool and return the group
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=cooldown,
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            lc_name='execute_scheduled')
        group = create_group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group
