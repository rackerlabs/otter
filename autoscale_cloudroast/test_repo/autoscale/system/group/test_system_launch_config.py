"""
System tests for launch config
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class LaunchConfigTest(AutoscaleFixture):

    """
    System tests to verify launch config
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(LaunchConfigTest, cls).setUpClass()
        cls.upd_server_name = "upd_lc_config"
        cls.upd_image_ref = cls.lc_image_ref_alt
        cls.upd_flavor_ref = "3"

    def test_system_update_launchconfig_scale_up(self):
        """
        Create a scaling group with a scaling policy, update the launch config.
        Execute the scaling policy, the servers created from executing the policy
        are with the updated launch config
        """
        minentities = 1
        group = self._create_group(minentities=minentities, policy=True)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        active_list_b4_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        self._execute_policy(group)
        active_servers = minentities + (self.sp_change)
        active_list_after_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=active_servers)
        upd_lc_server = set(active_list_after_upd) - set(active_list_b4_upd)
        self._verify_server_list_for_launch_config(
            upd_lc_server, self.upd_server_name,
            self.upd_image_ref, self.upd_flavor_ref)
        self.empty_scaling_group(group)

    def test_system_update_launchconfig_scale_down(self):
        """
        Create a scaling group with a scale up and scale down policy. Execute the scale up
        policy, update launch config. Then executing the scale down policy deletes servers
        with older launch config
        """
        minentities = 1
        group = self._create_group(minentities=minentities, policy=True)
        scale_down_change = -1
        policy_down = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=scale_down_change,
            sp_cooldown=0)
        first_server = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        self._execute_policy(group)
        active_list_b4_upd = self.autoscale_behaviors.\
            wait_for_expected_number_of_active_servers(
                group_id=group.id,
                expected_servers=minentities + self.sp_change)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self._execute_policy(group, policy_down['id'])
        server_after_down = len(active_list_b4_upd) + scale_down_change
        active_server_list_after_scale_down = self.autoscale_behaviors.\
            wait_for_expected_number_of_active_servers(
                group_id=group.id,
                expected_servers=server_after_down)
        self.assertEqual(set(active_server_list_after_scale_down), (
            set(active_list_b4_upd) - set(first_server)))
        self._verify_server_list_for_launch_config(
            active_server_list_after_scale_down,
            group.launchConfiguration.server.name,
            group.launchConfiguration.server.imageRef,
            group.launchConfiguration.server.flavorRef)
        self.empty_scaling_group(group)

    def test_system_update_launchconfig_scale_up_down(self):
        """
        Create a scaling group with a scale up and scale down policy. Execute the scale up
        policy, update launch config. Then executing the scale down and scale up policy,
        deletes servers with older launch config and launches servers with the updated
        launch config
        """
        minentities = 1
        group = self._create_group(minentities=minentities, policy=True)
        first_server = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        scale_down_change = -1
        policy_down = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=scale_down_change,
            sp_cooldown=0)
        self._execute_policy(group)
        active_list_b4_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities + self.sp_change)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self._execute_policy(group)
        active_servers = minentities + (2 * self.sp_change)
        active_list_after_up = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=active_servers)
        upd_lc_server = set(active_list_after_up) - set(active_list_b4_upd)
        self._verify_server_list_for_launch_config(
            upd_lc_server, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self._execute_policy(group, policy_down['id'])
        server_after_down = active_servers + scale_down_change
        active_list_after_down = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=server_after_down)
        self.assertEqual(set(active_list_after_down), (
            set(active_list_after_up) - set(first_server)))
        self.empty_scaling_group(group)

    def test_system_server_details_name_and_metadata(self):
        """
        Server name is appended by random characters and metadata of servers includes the group id,
        for servers created by autoscale.
        """
        server_name = 'test_server_details'
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_name=server_name)
        group = create_group_response.entity
        active_servers_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minEntities)
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
        Updates to the launch config do not apply to the servers building,
        when the update is made
        """
        minentities = 2
        group = self._create_group(minentities=minentities)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        servers_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        self._verify_server_list_for_launch_config(
            servers_list,
            group.launchConfiguration.server.name,
            group.launchConfiguration.server.imageRef,
            group.launchConfiguration.server.flavorRef)
        self.empty_scaling_group(group)

    def test_system_update_launchconfig_group_minentities(self):
        """
        Create a scaling group, update the launch config.
        Update the minentities to be more than when the group was created,
        the newly created servers to match the updated minentities, are of the
        latest launch config
        """
        minentities = 1
        upd_minentities = 3
        group = self._create_group(minentities=minentities)
        servers_first_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        self._verify_server_list_for_launch_config(
            servers_first_list,
            group.launchConfiguration.server.name,
            group.launchConfiguration.server.imageRef,
            group.launchConfiguration.server.flavorRef)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        update_group_response = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=upd_minentities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(update_group_response.status_code, 204)
        servers_list_on_upd = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=upd_minentities)
        servers_from_upd = set(servers_list_on_upd) - set(servers_first_list)
        self._verify_server_list_for_launch_config(
            servers_from_upd, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self.empty_scaling_group(group)

    def test_system_update_launchconfig_group_maxentities(self):
        """
        Create a scaling group with scaling policy and with minentities=sp_change in the scaling policy.
        Update the launch config, execute policy, new servers are of updated launch config.
        Update the maxentities=minentities=sp_change, hence causing scale down by same number as
        the scale up. Resulting servers are of updated launch config only. (sp_change from config)
        """
        minentities = self.sp_change
        group = self._create_group(
            minentities=minentities, policy=True)
        servers_list_b4_upd = self.autoscale_behaviors.\
            wait_for_expected_number_of_active_servers(
                group_id=group.id,
                expected_servers=minentities)
        self._verify_server_list_for_launch_config(
            servers_list_b4_upd,
            group.launchConfiguration.server.name,
            group.launchConfiguration.server.imageRef,
            group.launchConfiguration.server.flavorRef)
        self._update_launch_config(
            group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self._execute_policy(group)
        active_list_after_upd_lc = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities + self.sp_change)
        servers_after_scale_up = set(
            active_list_after_upd_lc) - set(servers_list_b4_upd)
        self._verify_server_list_for_launch_config(
            servers_after_scale_up, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        update_group_response = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=group.groupConfiguration.minEntities,
            max_entities=group.groupConfiguration.minEntities,
            metadata={})
        self.assertEquals(update_group_response.status_code, 204)
        self._execute_policy(group)
        servers_list_on_upd_group = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=group.groupConfiguration.minentities)
        active_servers_on_upd_group = set(
            servers_list_on_upd_group) - set(active_list_after_upd_lc)
        self.assertEquals(set(active_servers_on_upd_group),
                         (set(active_list_after_upd_lc) - set(servers_list_b4_upd)))
        self._verify_server_list_for_launch_config(
            active_servers_on_upd_group, self.upd_server_name, self.upd_image_ref, self.upd_flavor_ref)
        self.empty_scaling_group(group)

    def test_system_scale_down_oldest_on_active_servers(self):
        """
        Create a scaling group with minentities=scale up=scale_down=sp_change(from config).
        Scale down and verify that the oldest server is scaled down first
        """
        minentities = self.sp_change
        group = self._create_group(minentities=minentities, policy=True)
        scale_down_change = - self.sp_change
        policy_down = self.autoscale_behaviors.create_policy_given(
            group_id=group.id,
            sp_change=scale_down_change,
            sp_cooldown=0)
        first_server = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group_id=group.id,
            expected_servers=minentities)
        self._execute_policy(group)
        active_list_after_scale_up = self.autoscale_behaviors.\
            wait_for_expected_number_of_active_servers(
                group_id=group.id,
                expected_servers=minentities + self.sp_change)
        servers_from_scale_up = set(
            active_list_after_scale_up) - set(first_server)
        self._execute_policy(group, policy_down['id'])
        active_server_list_after_scale_down = self.autoscale_behaviors.\
            wait_for_expected_number_of_active_servers(
                group_id=group.id,
                expected_servers=self.sp_change)
        self.assertEqual(set(servers_from_scale_up), set(
            active_server_list_after_scale_down))

    def _create_group(self, minentities=None, maxentities=None, policy=False):
        """
        Create a scaling group with the given minentities, maxentities,
        and cooldown as 0. Create group with scaling policy if policy is set to True.
        Return the group.
        """
        if policy is True:
            sp_list = [{'name': "policy in group",
                        'change': self.sp_change,
                        'cooldown': 0,
                        'type': 'webhook'
                        }]
            create_group_response = self.autoscale_behaviors.create_scaling_group_given(
                gc_min_entities=minentities, gc_max_entities=maxentities,
                gc_cooldown=0, sp_list=sp_list)
        else:
            create_group_response = self.autoscale_behaviors.create_scaling_group_given(
                gc_min_entities=minentities, gc_max_entities=maxentities,
                gc_cooldown=0)
        group = create_group_response.entity
        self.assertEqual(create_group_response.status_code, 201,
                         msg='Create group failed with {0}'.format(group.id))
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group

    def _update_launch_config(self, group, server_name=None, image_ref=None,
                              flavor_ref=None):
        """
        Update the scaling group's launch configuration and
        assert the update was successful.
        """
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=server_name,
            image_ref=image_ref,
            flavor_ref=flavor_ref)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config failed with {0} for group {1}'
                          .format(update_launch_config_response, group.id))

    def _verify_server_list_for_launch_config(self, server_list,
                                              upd_server_name,
                                              upd_image_ref,
                                              upd_flavor_ref):
        for each in list(server_list):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertTrue(upd_server_name in server.name)
            self.assertEquals(server.image.id, upd_image_ref)
            self.assertEquals(server.flavor.id, upd_flavor_ref)

    def _execute_policy(self, group, policy_id=None):
        """
        If policy_id is given, execute that policy in the scaling group,
        else execute the policy the group was created with
        """
        if policy_id is None:
            policy_id = self.autoscale_behaviors.get_policy_properties(
                group.scalingPolicies)['id']

        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=group.id,
            policy_id=policy_id)
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy failed to execute with status {0} for group {1}'
                          .format(execute_policy_response.status_code, group.id))
