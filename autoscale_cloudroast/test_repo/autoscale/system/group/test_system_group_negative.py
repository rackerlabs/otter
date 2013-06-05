"""
System tests for negative groups scenarios
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture
from time import sleep
import unittest


class NegativeGroupFixture(ScalingGroupWebhookFixture):

    """
    System tests to verify negative scaling group scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(NegativeGroupFixture, cls).setUpClass()
        cls.invalid_lbaas = [{'loadBalancerId': 0000, 'port': 0000}]

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(NegativeGroupFixture, cls).tearDownClass()

    def test_system_create_delete_scaling_group_invalid_imageid(self):
        """
        Verify create and delete scaling group with invalid server image id
         Note: the group state table is first updated with expected, then tries nova and updates to 0
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_image_ref="INVALIDIMAGEID")
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
                          msg='Create group with invalid server image id failed with %s'
                          % create_group_response.status_code)
        sleep(2)
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity +
            group_state.activeCapacity, 0,
            msg='Group failed to attempt to create server with invalid image. Active+pending != min')
        self.assertEqual(group_state.desiredCapacity, 0,
                         msg='Desired capacity is not equal to the minentities on the group')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Deleted group failed for a group with invalid server image ID with %s'
                          % delete_group_response.status_code)

    def test_system_execute_policy_with_invalid_imageid(self):
        """
        Verify execute policy with invalid server image id
        Note: the group state table is first updated with expected, then tries nova and updates to 0
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
        sleep(2)
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

    @unittest.skip("Invalid LbaasID handling not implemented")
    def test_system_create_delete_scaling_group_invalid_lbaasid(self):
        """
        Verify create and delete scaling group with invalid lbaas id
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_load_balancers=self.invalid_lbaas)
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
                          msg='Create group with invalid lbaas id failed with %s'
                          % create_group_response.status_code)
        #check active servers and wait for lbaas add node to fail
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity +
            group_state.activeCapacity, 0,
            msg='Group failed to attempt to create server with invalid lbaas id. Active+pending != min')
        self.assertEqual(group_state.desiredCapacity, 0,
                         msg='Desired capacity is not equal to the minentities on the group')
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id)
        self.assertEquals(delete_group_response.status_code, 204,
                          msg='Deleted group failed for a group with invalid lbaas id with %s'
                          % delete_group_response.status_code)

    @unittest.skip("Invalid LbaasID handling not implemented")
    def test_system_execute_policy_with_invalid_lbaasid(self):
        """
        Verify execute policy with invalid lbaas id
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
        #check active servers and wait for lbaas add node to fail
        group_state_response = self.autoscale_client.list_status_entities_sgroups(
            self.group.id)
        self.assertEquals(group_state_response.status_code, 200)
        group_state = group_state_response.entity
        self.assertEquals(
            group_state.pendingCapacity + group_state.activeCapacity,
            0,
            msg='Active + Pending servers is not equal to expected number of servers')
        self.assertEqual(group_state.desiredCapacity, 0,
                         msg='Desired capacity is not equal to expected number of servers')

    def test_system_delete_group_delete_all_servers(self):
        """
        Verify delete scaling group when user deletes all the servers on the group
        """
        pass

    def test_system_delete_group_delete_some_servers(self):
        """
        Verify delete scaling group when user deletes some of the servers on the group
        """
        pass

    def test_system_delete_group_other_server_actions(self):
        """
        Verify delete scaling group when user performs actions on the servers in the group
        """
        pass

    def test_system_create_delete_scaling_group_server_building_indefinitely(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_execute_policy_server_building_indefinitely(self):
        """
        Verify execute policy when servers build indefinitely
        """
        pass

    def test_system_execute_policy_one_ofthe_server_builds_indefinitely(self):
        """
        Verify execute policy when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_some_servers_error(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_all_servers_error(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_server_rate_limit_met(self):
        """
        Verify create delete group when maximum servers allowed already exist.
        """
        pass

    def test_system_execute_policy_when_server_rate_limit_met(self):
        """
        Verify execute policy when maximum servers allowed already exist.
        """
        pass

    def test_system_create_scaling_group_account_suspended(self):
        """
        Verify create scaling group when account is suspended
        """
        pass

    def test_system_execute_policy_on_suspended_account(self):
        """
        Verify create scaling group when account is suspended
        """
        pass

    def test_system_create_scaling_group_account_closed(self):
        """
        Verify create scaling group when account is closed
        """
        pass

    def test_system_execute_policy_on_closed_account(self):
        """
        Verify create scaling group when account is closed
        """
        pass

    def test_system_delete_group_unable_to_impersonate(self):
        """
        Verify delete scaling group when impersonation fails
        """
        # AUTO - 284
        pass

    def test_system_delete_group_when_nova_down(self):
        """
        Verify delete scaling group when nova is down
        """
        pass

    def test_system_delete_group_when_lbaas_down(self):
        """
        Verify delete scaling group when lbaas is down
        """
        pass

    def test_system_scaling_group_lbaas_draining_disabled(self):
        """
        Verify execute policy with lbaas draining or disabled
        """
        pass

    def test_system_create_delete_scaling_group_with_deleted_lbaasid(self):
        """
        Verify creation of scaling group with deleted lbaas id
        note : is this same as invalid id??
        """
        pass

    def test_system_execute_policy_with_deleted_lbaasid(self):
        """
        Verify polic execution with deleted lbaas id
        note : is this same as invalid id??
        """
        pass
