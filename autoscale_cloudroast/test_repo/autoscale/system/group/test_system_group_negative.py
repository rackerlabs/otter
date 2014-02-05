"""
System tests for negative groups scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest
from cafe.drivers.unittest.decorators import tags


class NegativeGroupFixture(AutoscaleFixture):

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

    @unittest.skip("Invalid LbaasID handling not implemented")
    def test_system_create_delete_scaling_group_invalid_lbaasid(self):
        """
        Verify scaling group fails when launch config has an invalid lbaasId
        and that it can be deleted
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_load_balancers=self.invalid_lbaas)
        group = create_group_response.entity
        self.assertEquals(create_group_response.status_code, 201,
                          msg='Create group with invalid lbaas id failed with {0}'
                          .format(create_group_response.status_code))
        # check active servers and wait for lbaas add node to fail
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
                          msg='Deleted group failed for a group with invalid lbaas id with {0}'
                          .format(delete_group_response.status_code))

    @unittest.skip("Invalid LbaasID handling not implemented")
    def test_system_execute_policy_with_invalid_lbaasid(self):
        """
        Verify scaling policy execution fails when launch config has an invalid lbaasId
        and that it can be deleted
        """
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=self.group.launchConfiguration.server.name,
            image_ref=self.group.launchConfiguration.server.imageRef,
            flavor_ref=self.group.launchConfiguration.server.flavorRef,
            load_balancers=self.invalid_lbaas)
        self.assertEquals(update_launch_config_response.status_code, 204,
                          msg='Updating launch config with invalid lbaas id failed with {0}'
                          .format(update_launch_config_response))
        execute_policy_response = self.autoscale_client.execute_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'])
        self.assertEquals(execute_policy_response.status_code, 202,
                          msg='Policy executed with an invalid lbaas id with status {0}'
                          .format(execute_policy_response.status_code))
        # check active servers and wait for lbaas add node to fail
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

    @tags(speed='quick')
    def test_system_user_delete_some_servers_out_of_band(self):
        """
        Create a group with 4 minentities and verify the group state when user deletes one
        of the servers on the group
        """
        server_count = 4
        group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=server_count, lc_metadata={'server_building': 30})
        group = group_response.entity
        self.assertEqual(group.state.pending, server_count,
                         msg='{0} servers are building. Expected {1}'.format(group.state.pending,
                                                                             server_count))
        server_list = self.get_servers_containing_given_name_on_tenant(group_id=group.id)
        self.assertEqual(len(server_list), server_count, msg='The number of servers building'
                         'is {0}, but should be {1} for group {2}'.format(len(server_list), server_count,
                                                                          group.id))
        self.server_client.delete_server(server_list[0])
        self.assertEqual(group.state.pending, server_count - 1,
                         msg='{0} servers are building. Expected {1}'.format(group.state.pending,
                                                                             server_count - 1))

    def test_system_create_delete_scaling_group_server_building_indefinitely(self):
        """
        Verify create delete scaling group when servers remain in 'build' state
        indefinitely
        """
        pass

    def test_system_execute_policy_server_building_indefinitely(self):
        """
        Verify execute policy when servers remain in build indefinitely
        """
        pass

    def test_system_execute_policy_one_ofthe_server_builds_indefinitely(self):
        """
        Verify execute policy when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_some_servers_error(self):
        """
        Verify create delete scaling group when servers some servers go
        into error state
        """
        pass

    def test_system_create_delete_scaling_group_all_servers_error(self):
        """
        Verify create delete scaling group when all the servers go into
        error state
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

    def test_system_delete_group_delete_all_servers(self):
        """
        Verify delete scaling group when user deletes all the servers on the group
        Autoscaling will re create all the deleted servers
        (try changing launch config jus before delete)
        """
        pass

    def test_system_delete_group_other_server_actions(self):
        """
        Verify delete scaling group when user performs actions on the servers in the group
        Autoscaling will continue, like no action occured
        """
        pass
