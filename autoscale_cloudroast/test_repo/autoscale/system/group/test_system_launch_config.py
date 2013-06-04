"""
System tests for launch config
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class LaunchConfigFixture(AutoscaleFixture):

    """
    System tests to verify launch config
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(LaunchConfigFixture, cls).setUpClass()
        cls.invalid_lbaas = [{'loadBalancerId': 0000, 'port': 0000}]

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(LaunchConfigFixture, cls).tearDownClass()

    def test_system_create_delete_scaling_group_invalid_imageid(self):
        """
        Verify create and delete scaling group with invalid server image id
        TBD: Verify the group state updates to be 0 when server image is invalid
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_image_ref="INVALIDIMAGEID")
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
                          msg='Create group with invalid server image id failed with %s'
                          % create_group_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity +
            group_state.activeCapacity, self.gc_min_entities_alt,
            msg='Group failed to attempt to create server with invalid image. Active+pending != min')
        self.assertEqual(group_state.desiredCapacity, self.gc_min_entities_alt,
                         msg='Desired capacity is not equal to the minentities on the group')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Deleted group failed for a group with invalid server image ID with %s'
                          % delete_group_response.status_code)

    def test_system_execute_policy_with_invalid_imageid(self):
        """
        Verify execute policy with invalid server image id
        TBD: Verify the group state updates to be 0 when server image is invalid
        """
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=self.group.launchConfiguration.server.name,
            image_ref="INVALIDIMAGEID",
            flavor_ref=self.group.launchConfiguration.server.flavorRef)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config with invalid image id faile with %s'
                          % update_launch_config_response)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='policy executed with an invalid server image id with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            self.gc_min_entities,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, self.gc_min_entities,
    msg='Desired capacity is not equal to expected number of servers')

    def test_system_create_delete_scaling_group_invalid_lbaasid(self):
        """
        Verify create and delete scaling group with invalid lbaas id
        TBD : Do we not create a server when lbaas ID is invalid
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_load_balancers=invalid_lbaas)
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
                          msg='Create group with invalid lbaas id failed with %s'
                          % create_group_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity +
            group_state.activeCapacity, self.gc_min_entities_alt,
            msg='Group failed to attempt to create server with invalid lbaas id. Active+pending != min')
        self.assertEqual(group_state.desiredCapacity, self.gc_min_entities_alt,
                         msg='Desired capacity is not equal to the minentities on the group')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Deleted group failed for a group with invalid lbaas id with %s %s'
                          % (delete_group_response.status_code, delete_group_response.message))

    def test_system_execute_policy_with_invalid_lbaasid(self):
        """
        Verify execute policy with invalid lbaas id
        TBD: Verify the group state updates to be 0 when lbaas data is invalid
        """
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=self.group.launchConfiguration.server.name,
            image_ref=self.group.launchConfiguration.server.imageRef,
            flavor_ref=self.group.launchConfiguration.server.flavorRef,
            load_balancers=self.invalid_lbaas)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config with invalid lbaas id failed with %s'
                          % update_launch_config_response)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy executed with an invalid lbaas id with status %s'
                          % execute_policy_response.status_code)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            self.gc_min_entities,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, self.gc_min_entities,
    msg='Desired capacity is not equal to expected number of servers')

    def test_system_update_launchconfig_scale_up(self):
        """
        Verify execute policies to scale up with multiple updates to launch config.
        Needs mock implementation of verifying the create server call
        after launch config is updated.
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
            active_servers=active_servers_1,
            interval_time=60)
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy failed to execute with status %s'
                          % execute_policy_response.status_code)
        active_servers = minentities + (1 * self.sp_change)
        active_list_after_upd = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=active_servers,
            interval_time=60)
        upd_lc_server = set(active_list_after_upd) - set(active_list_b4_upd)
        for each in list(upd_lc_server):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, upd_image_ref)
            self.assertEquals(server.flavor.id, upd_flavor_ref)

    def test_system_update_launchconfig_scale_down(self):
        """
        Verify execute policies to scale down with multiple updates to launch config.
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
        policy_down = self.autoscale_behaviors.create_policy_min(
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
        server_after_down = active_list_b4_upd + scale_down_change
        active_list_after_down = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=server_after_down)
        self.assertEqual(set(active_list_after_down), (set(active_list_b4_upd)-set(first_server)))
        for each in list(active_list_after_down):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertEquals(server.image.id, self.lc_image_ref)
            self.assertEquals(server.flavor.id, self.lc_flavor_ref)

    def test_system_update_launchconfig_scale_up_down(self):
        """
        Verify execute policies to scale up and down with updates to launch config.
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
        policy_down = self.autoscale_behaviors.create_policy_min(
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
        self.assertEqual(set(active_list_after_down), (set(active_list_after_up)-set(first_server)))

    def test_system_server_details_name_and_metadata(self):
        """
        Verify server name and metadata of servers in a scaling group.
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
            self.assertEquals(server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(server.flavor.id, group.launchConfiguration.server.flavorRef)
            self.assertEquals(metadata, expected_metadata)
            self.assertTrue(server_name in server.name)

    def test_system_update_launchconfig_while_group_building(self):
        """
        Verify group when launch config is updated while policy is executing.
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
            self.assertEquals(server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(server.flavor.id, group.launchConfiguration.server.flavorRef)

    def test_system_update_launchconfig_group_minentities(self):
        """
        Verify group when launch config is updated and then minentities are increased.
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
            self.assertEquals(server.image.id, group.launchConfiguration.server.imageRef)
            self.assertEquals(server.flavor.id, group.launchConfiguration.server.flavorRef)
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
