"""
System tests for launch config
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class LaunchConfigFixture(ScalingGroupWebhookFixture):

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

    # def test_system_create_delete_scaling_group_invalid_imageid(self):
    #     """
    #     Verify create and delete scaling group with invalid server image id
    #     TBD: Verify the group state updates to be 0 when server image is invalid
    #     """
    #     create_group_response = self.autoscale_behaviors.create_scaling_group_given(
    #         gc_min_entities=self.gc_min_entities_alt,
    #         lc_image_ref="INVALIDIMAGEID")
    #     group = create_group_response.entity
    #     self.assertEquals(create_group_response.status_code, 201,
    #                       msg='Create group with invalid server image id failed with %s'
    #                       % create_group_response.status_code)
    #     group_state_response = self.autoscale_client.list_status_entities_sgroups(
    #         group.id)
    #     self.assertEquals(group_state_response.status_code, 200)
    #     group_state = group_state_response.entity
    #     self.assertEquals(
    #         group_state.pendingCapacity +
    #         group_state.activeCapacity, self.gc_min_entities_alt,
    #         msg='Group failed to attempt to create server with invalid image. Active+pending != min')
    #     self.assertEqual(group_state.desiredCapacity, self.gc_min_entities_alt,
    #                      msg='Desired capacity is not equal to the minentities on the group')
    #     delete_group_response = self.autoscale_client.delete_scaling_group(
    #         group.id)
    #     self.assertEquals(delete_group_response.status_code, 204,
    #                       msg='Deleted group failed for a group with invalid server image ID with %s'
    #                       % delete_group_response.status_code)

    # def test_system_execute_policy_with_invalid_imageid(self):
    #     """
    #     Verify execute policy with invalid server image id
    #     TBD: Verify the group state updates to be 0 when server image is invalid
    #     """
    #     update_launch_config_response = self.autoscale_client.update_launch_config(
    #         group_id=self.group.id,
    #         name=self.group.launchConfiguration.server.name,
    #         image_ref="INVALIDIMAGEID",
    #         flavor_ref=self.group.launchConfiguration.server.flavorRef)
    #     self.assertEquals(update_launch_config_response.status_code, 204,
    #                       msg='Updating launch config with invalid image id faile with %s'
    #                       % update_launch_config_response)
    #     execute_policy_response = self.autoscale_client.execute_policy(
    #         group_id=self.group.id,
    #         policy_id=self.policy['id'])
    #     self.assertEquals(execute_policy_response.status_code, 202,
    #                       msg='policy executed with an invalid server image id with status %s'
    #                       % execute_policy_response.status_code)
    #     group_state_response = self.autoscale_client.list_status_entities_sgroups(
    #         self.group.id)
    #     self.assertEquals(group_state_response.status_code, 200)
    #     group_state = group_state_response.entity
    #     self.assertEquals(
    #         group_state.pendingCapacity + group_state.activeCapacity,
    #         self.gc_min_entities,
    #         msg='Active + Pending servers is not equal to expected number of servers')
    #     self.assertEqual(group_state.desiredCapacity, self.gc_min_entities,
    # msg='Desired capacity is not equal to expected number of servers')

    # def test_system_create_delete_scaling_group_invalid_lbaasid(self):
    #     """
    #     Verify create and delete scaling group with invalid lbaas id
    #     TBD : Do we not create a server when lbaas ID is invalid
    #     """
    #     create_group_response = self.autoscale_behaviors.create_scaling_group_given(
    #         gc_min_entities=self.gc_min_entities_alt,
    #         lc_load_balancers=invalid_lbaas)
    #     group = create_group_response.entity
    #     self.assertEquals(create_group_response.status_code, 201,
    #                       msg='Create group with invalid lbaas id failed with %s'
    #                       % create_group_response.status_code)
    #     group_state_response = self.autoscale_client.list_status_entities_sgroups(
    #         group.id)
    #     self.assertEquals(group_state_response.status_code, 200)
    #     group_state = group_state_response.entity
    #     self.assertEquals(
    #         group_state.pendingCapacity +
    #         group_state.activeCapacity, self.gc_min_entities_alt,
    #         msg='Group failed to attempt to create server with invalid lbaas id. Active+pending != min')
    #     self.assertEqual(group_state.desiredCapacity, self.gc_min_entities_alt,
    #                      msg='Desired capacity is not equal to the minentities on the group')
    #     delete_group_response = self.autoscale_client.delete_scaling_group(
    #         group.id)
    #     self.assertEquals(delete_group_response.status_code, 204,
    #                       msg='Deleted group failed for a group with invalid lbaas id with %s %s'
    #                       % (delete_group_response.status_code, delete_group_response.message))

    # def test_system_execute_policy_with_invalid_lbaasid(self):
    #     """
    #     Verify execute policy with invalid lbaas id
    #     TBD: Verify the group state updates to be 0 when lbaas data is invalid
    #     """
    #     update_launch_config_response = self.autoscale_client.update_launch_config(
    #         group_id=self.group.id,
    #         name=self.group.launchConfiguration.server.name,
    #         image_ref=self.group.launchConfiguration.server.imageRef,
    #         flavor_ref=self.group.launchConfiguration.server.flavorRef,
    #         load_balancers=self.invalid_lbaas)
    #     self.assertEquals(update_launch_config_response.status_code, 204,
    #                       msg='Updating launch config with invalid lbaas id failed with %s'
    #                       % update_launch_config_response)
    #     execute_policy_response = self.autoscale_client.execute_policy(
    #         group_id=self.group.id,
    #         policy_id=self.policy['id'])
    #     self.assertEquals(execute_policy_response.status_code, 202,
    #                       msg='Policy executed with an invalid lbaas id with status %s'
    #                       % execute_policy_response.status_code)
    #     group_state_response = self.autoscale_client.list_status_entities_sgroups(
    #         self.group.id)
    #     self.assertEquals(group_state_response.status_code, 200)
    #     group_state = group_state_response.entity
    #     self.assertEquals(
    #         group_state.pendingCapacity + group_state.activeCapacity,
    #         self.gc_min_entities,
    #         msg='Active + Pending servers is not equal to expected number of servers')
    #     self.assertEqual(group_state.desiredCapacity, self.gc_min_entities,
    # msg='Desired capacity is not equal to expected number of servers')

    def test_system_update_launchconfig_scale_up(self):
        """
        Verify execute policies to scale up with multiple updates to launch config.
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=1)
        group = create_group_response.entity
        resp = self.autoscale_behaviors.wait_for_active_list_in_group_state(
            group_id=group.id,
            active_servers=1)
        print resp
        # execute_policy_response = self.autoscale_client.execute_policy(
        #     group_id=self.group.id,
        #     policy_id=self.policy['id'])
        # self.assertEquals(execute_policy_response.status_code, 202,
        #                   msg='Scale up policy failed to execute with status %s'
        #                   % execute_policy_response.status_code)
        # upd_server_name = "upd_lc_config"
        # upd_image_ref = "76765765_TBD"
        # upd_flavor_ref = "3"
        # update_launch_config_response = self.autoscale_client.update_launch_config(
        #     group_id=self.group.id,
        #     name=upd_server_name,
        #     image_ref=upd_image_ref,
        #     flavor_ref=upd_flavor_ref)
        # self.assertEquals(update_launch_config_response.status_code, 204,
        #                   msg='Updating launch config with invalid lbaas id failed with %s'
        #                   % update_launch_config_response)
        # execute_policy_response = self.autoscale_client.execute_policy(
        #     group_id=self.group.id,
        #     policy_id=self.policy['id'])
        # self.assertEquals(execute_policy_response.status_code, 202,
        #                   msg='Policy executed with an invalid lbaas id with status %s'
        #                   % execute_policy_response.status_code)


    # def test_system_update_launchconfig_scale_down(self):
    #     """
    #     Verify execute policies to scale down with multiple updates to launch config.
    #     """
    #     pass

    # def test_system_update_launchconfig_scale_up_down(self):
    #     """
    #     Verify execute policies to scale up and down with updates to launch config.
    #     """
    #     pass

    # def test_system_update_launchconfig_while_group_building(self):
    #     """
    #     Verify group when launch config is updated while policy is executing.
    #     """
    #     pass

    # def test_system_scaling_group_lbaas_draining_disabled(self):
    #     """
    #     Verify execute policy with lbaas draining or disabled
    #     """
    #     pass
