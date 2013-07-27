"""
Test execution of at and cron style scheduler policies when group has updates
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
import unittest


class UpdateSchedulerScalingPolicy(AutoscaleFixture):

    """
    Verify update scheduler policy
    """
    @classmethod
    def setUpClass(cls):
        """
        Define updates to launch config
        """
        super(UpdateSchedulerScalingPolicy, cls).setUpClass()
        cls.upd_server_name = "upd_lc_config"
        cls.upd_image_ref = cls.lc_image_ref_alt
        cls.upd_flavor_ref = "3"

    def test_system_min_max_entities_at_style(self):
        """
        Create a scaling group with minentities between 0 and maxentities and
        maxentities=change, with 2 at style scheduler policies with change= +2 and -2,
        cooldown=0 and verify that the scale up scheduler policy scales upto the
        max entities specified on the group
        and scale down scheduler policy scales down upto the minentities.
        """
        minentities = 1
        maxentities = 2
        group = self._create_group(
            cooldown=0, minentities=minentities, maxentities=maxentities)
        self.create_default_at_style_policy_wait_for_execution(
            group_id=group.id, change=maxentities + 1)
        self.verify_group_state(group.id, group.groupConfiguration.maxEntities)
        self.create_default_at_style_policy_wait_for_execution(
            group_id=group.id, change=maxentities,
            scale_down=True)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        self.empty_scaling_group(group)

    @unittest.skip('AUTO-442')
    def test_system_min_max_entities_cron_style(self):
        """
        Create a scaling group with minentities between 0 and maxentities and maxentities=change,
        with 2 cron style scheduler policies with change= +2 and -2, cooldown=0 and verify that
        the scale up scheduler policy scales upto the maxentities specified on the group
        and scale down scheduler policy scales down upto the minentities.
        Note: The group and policy cooldown are 0 and the scale up and scale down policies
        will keep trying to scale up beyond maxentities and scale down below minentities
        but will not be executed as min/maxenetities are met, until group is deleted.
        """
        minentities = 1
        maxentities = 2
        group = self._create_group(
            cooldown=0, minentities=minentities, maxentities=maxentities)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=maxentities + 1,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, group.groupConfiguration.maxEntities)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=0,
            sp_change=-maxentities,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(group.id, group.groupConfiguration.minEntities)
        self.empty_scaling_group(group)

    def test_system_group_cooldown_atstyle(self):
        """
        Create a scaling group with cooldown>0, create a scheduler at style policy
        and wait for its execution, creating another at style policy scheduled
        to execute before the cooldown period expires does not trigger.
        Creating a 3rd at style policy after the cooldown, executes successfully.
        """
        group = self._create_group(cooldown=60)
        self.create_default_at_style_policy_wait_for_execution(group.id)
        self.verify_group_state(group.id, self.sp_change)
        self.create_default_at_style_policy_wait_for_execution(group.id)
        self.verify_group_state(group.id, self.sp_change)
        sleep(60 - self.scheduler_interval)
        self.create_default_at_style_policy_wait_for_execution(group.id)
        self.verify_group_state(group.id, self.sp_change * 2)
        self.empty_scaling_group(group)

    def test_system_upd_launch_config_at_style_scheduler(self):
        """
        Create a scaling group with minentities>0, update launch config, schedule at style
        policy to scale up and verify the new servers of the latest launch config,
        then schedule an at style policy to scale down and verify the servers remaining
        are of the latest launch config.
        """
        group = self._create_group(minentities=self.sp_change)
        active_list_b4_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minEntities)
        self._update_launch_config(group)
        self.create_default_at_style_policy_wait_for_execution(group.id)
        active_servers = self.sp_change + group.groupConfiguration.minEntities
        active_list_after_scale_up = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=active_servers)
        upd_lc_server = set(
            active_list_after_scale_up) - set(active_list_b4_upd)
        self._verify_server_list_for_launch_config(upd_lc_server)
        self.create_default_at_style_policy_wait_for_execution(
            group.id, scale_down=True)
        active_list_on_scale_down = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minEntities)
        self._verify_server_list_for_launch_config(active_list_on_scale_down)
        self.empty_scaling_group(group)

    @unittest.skip('AUTO-442')
    def test_system_upd_launch_config_cron_style_scheduler(self):
        """
        Create a scaling group with minentities>0, update launch config, schedule cron style
        policy to scale up and verify the new servers of the latest launch config,
        then schedule another cron style policy to scale down and verify the servers remaining
        are of the latest launch config.
        """
        group = self._create_group(minentities=self.sp_change)
        active_list_b4_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minEntities)
        self._update_launch_config(group)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=3600,
            sp_change=self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        active_servers = self.sp_change + group.groupConfiguration.minEntities
        active_list_after_scale_up = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=active_servers)
        upd_lc_server = set(
            active_list_after_scale_up) - set(active_list_b4_upd)
        self._verify_server_list_for_launch_config(upd_lc_server)
        self.autoscale_behaviors.create_schedule_policy_given(
            group_id=group.id,
            sp_cooldown=3600,
            sp_change=-self.sp_change,
            schedule_cron='* * * * *')
        sleep(60 + self.scheduler_interval)
        active_list_on_scale_down = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minEntities)
        self._verify_server_list_for_launch_config(active_list_on_scale_down)
        self.empty_scaling_group(group)

    def _create_group(self, cooldown=None, minentities=None, maxentities=None):
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=cooldown,
            gc_min_entities=minentities,
            gc_max_entities=maxentities,
            lc_name='upd_grp_scheduled')
        group = create_group_response.entity
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group

    def _update_launch_config(self, group):
        """
        Update the scaling group's launch configuration and
        assert the update was successful.
        """
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=self.upd_server_name,
            image_ref=self.upd_image_ref,
            flavor_ref=self.upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with {0} for group {1}'
                          .format(update_launch_config_response, group.id))

    def _verify_server_list_for_launch_config(self, server_list):
        for each in list(server_list):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertTrue(self.upd_server_name in server.name)
            self.assertEquals(server.image.id, self.lc_image_ref_alt)
            self.assertEquals(server.flavor.id, self.upd_flavor_ref)
