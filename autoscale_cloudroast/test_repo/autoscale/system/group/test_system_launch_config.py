"""
System tests for launch config
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class LaunchConfigTest(ScalingGroupWebhookFixture):

    """
    System tests to verify launch config
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(LaunchConfigTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(LaunchConfigTest, cls).tearDownClass()

    def test_system_update_launchconfig_scale_up(self):
        """
        Create a scaling group, update launch config and verify executing a policy
        creates servers with latest launch config
        """
        minentities = 1
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_cooldown=0)
        group = create_group_response.entity
        policy = self.autoscale_behaviors.create_policy_min(
            group_id=group.id,
            sp_cooldown=0)
        upd_server_name = "upd_lc_config"
        upd_image_ref = self.lc_image_ref_alt
        upd_flavor_ref = "3"
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=upd_server_name,
            image_ref=upd_image_ref,
            flavor_ref=upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with %s'
                          % update_launch_config_response)
        active_servers_1 = minentities
        active_list_b4_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers_1)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        active_servers = minentities + (1 * self.sp_change)
        active_list_after_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers)
        upd_lc_server = set(active_list_after_upd) - set(active_list_b4_upd)
        for each in list(upd_lc_server):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, upd_image_ref)
            self.assertEquals(server.flavor.id, upd_flavor_ref)

    def test_system_update_launchconfig_scale_down(self):
        """
        Create a scaling group and execute a scale up policy, update launch config
        and verify executing a scale down policy deletes servers with older launch config
        """
        minentities = 1
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_cooldown=0)
        group = create_group_response.entity
        first_server = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=minentities)
        policy_up = self.autoscale_behaviors.create_policy_min(
            group_id=group.id,
            sp_cooldown=0)
        scale_down_change = -1
        policy_down = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=scale_down_change,
            sp_cooldown=0)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_up['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Scale up policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        active_servers_1 = minentities + self.sp_change
        active_list_b4_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers_1)
        upd_server_name = "upd_lc_config"
        upd_image_ref = self.lc_image_ref_alt
        upd_flavor_ref = "3"
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=upd_server_name,
            image_ref=upd_image_ref,
            flavor_ref=upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with %s'
                          % update_launch_config_response)
        execute_policy_down_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_down['id'])
        self.assertEquals(execute_policy_down_response.status_code, 202,
                          msg='Scale down policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        server_after_down = len(active_list_b4_upd) + scale_down_change
        active_list_after_down = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=server_after_down)
        self.assertEqual(set(active_list_after_down), (
            set(active_list_b4_upd) - set(first_server)))
        for each in list(active_list_after_down):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, self.lc_image_ref)
            self.assertEquals(server.flavor.id, self.lc_flavor_ref)

    def test_system_update_launchconfig_scale_up_down(self):
        """
        Create a scaling group and execute a scale up policy, update launch config
        and verify executing a scale down policy deletes servers with older launch config,
        and executing a scale up policy creates servers with new launch configs
        """
        minentities = 1
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities,
            gc_cooldown=0)
        group = create_group_response.entity
        first_server = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=minentities)
        policy_up = self.autoscale_behaviors.create_policy_min(
            group_id=group.id,
            sp_cooldown=0)
        scale_down_change = -1
        policy_down = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=scale_down_change,
            sp_cooldown=0)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_up['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Scale up policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        upd_server_name = "upd_lc_config"
        upd_image_ref = self.lc_image_ref_alt
        upd_flavor_ref = "3"
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=upd_server_name,
            image_ref=upd_image_ref,
            flavor_ref=upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with %s'
                          % update_launch_config_response)
        active_servers_1 = minentities + self.sp_change
        active_list_b4_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers_1)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_up['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        active_servers = minentities + (2 * self.sp_change)
        active_list_after_up = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers)
        upd_lc_server = set(active_list_after_up) - set(active_list_b4_upd)
        for each in list(upd_lc_server):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, upd_image_ref)
            self.assertEquals(server.flavor.id, upd_flavor_ref)
        execute_policy_down_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_down['id'])
        self.assertEquals(execute_policy_down_response.status_code, 202,
                          msg='Scale down policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        server_after_down = active_servers + scale_down_change
        active_list_after_down = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=server_after_down)
        self.assertEqual(set(active_list_after_down), (
            set(active_list_after_up) - set(first_server)))

    def test_system_server_details_name_and_metadata(self):
        """
        Verify server name and metadata of servers created by autoscale
        in a scaling group
        """
        server_name = 'test_server_details'
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_name=server_name)
        group = create_group_response.entity
        active_servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=group.groupConfiguration.minEntities)
        expected_metadata = {'rax:auto_scaling_group_id': group.id}
        for each in list(active_servers_list):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            metadata = self.autoscale_behaviors.to_data(server.metadata)
            self.assertEquals(
                server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(
                server.flavor.id, group.launchConfiguration.server.flavorRef)
            self.assertEquals(metadata, expected_metadata)
            self.assertTrue(server_name in server.name)

    def test_system_update_launchconfig_while_group_building(self):
        """
        Verify that updates to a launch config do not apply to a policy that
        is executing when the update is made
        """
        minentities = 5
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        group = create_group_response.entity
        upd_server_name = "upd_lc_config"
        upd_image_ref = self.lc_image_ref_alt
        upd_flavor_ref = "3"
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=upd_server_name,
            image_ref=upd_image_ref,
            flavor_ref=upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with %s'
                          % update_launch_config_response)
        servers_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=minentities)
        for each in servers_list:
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(
                server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(
                server.flavor.id, group.launchConfiguration.server.flavorRef)

    def test_system_update_launchconfig_group_minentities(self):
        """
        Create a scaling group update the launch config and update the minentities,
        to be more and verify the newly created servers of the latest launch config
        """
        minentities = 1
        upd_minentities = 2
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=minentities)
        group = create_group_response.entity
        servers_first_list = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=minentities)
        for each in servers_first_list:
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(
                server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(
                server.flavor.id, group.launchConfiguration.server.flavorRef)
        upd_server_name = "upd_lc_config"
        upd_image_ref = self.lc_image_ref_alt
        upd_flavor_ref = "3"
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=upd_server_name,
            image_ref=upd_image_ref,
            flavor_ref=upd_flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with %s'
                          % update_launch_config_response)
        update_group_response = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=upd_minentities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(update_group_response.status_code, 204)
        servers_list_on_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=upd_minentities)
        servers_from_upd = set(servers_list_on_upd) - set(servers_first_list)
        for each in list(servers_from_upd):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, upd_image_ref)
            self.assertEquals(server.flavor.id, upd_flavor_ref)
