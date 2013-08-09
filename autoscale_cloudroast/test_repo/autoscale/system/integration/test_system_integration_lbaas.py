"""
System Integration tests autoscaling with lbaas
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags
import random
import unittest
import time


class AutoscaleLbaasFixture(AutoscaleFixture):

    """
    System tests to verify lbaas integration with autoscale
    """

    @tags(speed='slow')
    def test_add_multiple_lbaas_to_group(self):
        """
        Adding multiple load balancers within the launch config when creating the group,
        cause the servers to be added as nodes to all the load balancers
        """
        group = self._create_group_given_lbaas_id(self.load_balancer_1,
                                                  self.load_balancer_2, self.load_balancer_3)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
                                                        self.load_balancer_1,
                                                        self.load_balancer_2,
                                                        self.load_balancer_3)

    @tags(speed='slow')
    def test_update_launch_config_to_include_multiple_lbaas(self):
        """
        Updating the launch config to add multiple load balancer to a group that had
        only one load balancer, results in the new servers of that group to be added
        as nodes to all the load balancers
        """
        policy_data = {'change': self.sp_change}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
                                                        self.load_balancer_1)
        self._update_launch_config(group, self.load_balancer_1, self.load_balancer_2,
                                   self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_data, execute_policy=True)
        activeservers_after_scale = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt + self.sp_change)
        active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
                                                        self.load_balancer_1,
                                                        self.load_balancer_2,
                                                        self.load_balancer_3)

    @tags(speed='slow')
    def test_update_launch_config_to_include_lbaas(self):
        """
        Update the launch config to add a load balancer to a group that did not
        have a load balancer, results in the new servers of that group to be added
        as nodes to the load balancers
        """
        policy_data = {'change': self.sp_change}
        group = (self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt)).entity
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._update_launch_config(group, self.load_balancer_1, self.load_balancer_2,
                                   self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_data, execute_policy=True)
        activeservers_after_scale = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt + self.sp_change)
        active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
                                                        self.load_balancer_1,
                                                        self.load_balancer_2,
                                                        self.load_balancer_3)

    @tags(speed='slow')
    def test_update_existing_lbaas_in_launch_config(self):
        """
        Create a scaling group with a given load balancer and verify the servers on the scaling group
        are added as nodes on the load balancer.
        Update the group's launch config to a different loadbalancer scale up and verify that the new
        servers are added to the newly update loadbalancer.
        Scale down and verify that servers with the older launch config are deleted i.e. the load
        balancer added during group creation no longer has the nodes from the scaling group.
        """
        policy_up_data = {'change': self.gc_min_entities_alt}
        policy_down_data = {'change': -self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
                                                        self.load_balancer_1)
        self._update_launch_config(group, self.load_balancer_2)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
        activeservers_after_scale = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt * 2)
        active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
                                                        self.load_balancer_2)
        scaled_down_server_ip = self._get_ipv4_address_list_on_servers(active_server_list)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_down_data, execute_policy=True)
        activeservers_scaledown = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, activeservers_scaledown,
                                                        self.load_balancer_2)
        lb_node_list = [each_node.address for each_node in self._get_node_list_from_lb(
            self.load_balancer_1)]
        self.assertTrue(set(scaled_down_server_ip) not in set(lb_node_list))

    @unittest.skip('AUTO-504')
    def test_delete_group_when_autoscale_server_is_the_last_node_on_lb(self):
        """
        Create a scaling group with load balancer. After the servers on the group are added to
        the loadbalancer, delete the older node with which the lb was created. Update minentities
        on the group to scale down and delete group.
        """
        load_balancer = self.load_balancer_3
        lb_node_id_list_before_scale = [each_node.id for each_node in self._get_node_list_from_lb(
            load_balancer)]
        group = self._create_group_given_lbaas_id(load_balancer)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
                                                        load_balancer)
        lb_node_addresses_list = [each_node.address for each_node in self._get_node_list_from_lb(
            load_balancer)]
        for each_node_id in lb_node_id_list_before_scale:
            self.lbaas_client.delete_node(load_balancer, each_node_id)
        self.assert_servers_deleted_successfully(group.launchConfiguration.server.name)
        # will the same server ip remain as node on load balancer? if not validate
        server_ip = self._get_ipv4_address_list_on_servers(active_server_list)
        self.assertTrue(set(server_ip) not in set(lb_node_addresses_list))

    @tags(speed='slow')
    def test_existing_nodes_on_lb_unaffected_by_scaling(self):
        """
        Get load balancer node id list before anyscale operation, create a scaling group
        with minentities>1, scale up and then scale down. After each scale operation,
        verify the nodes existing on the load balancer before any scale operation persists
        """
        load_balancer = self.load_balancer_1
        lb_node_list_before_scale = [each_node.address for each_node in
                                     self._get_node_list_from_lb(load_balancer)]
        policy_up_data = {'change': self.gc_min_entities_alt}
        policy_down_data = {'change': -self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(load_balancer)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt * 2)
        self._assert_lb_nodes_before_scale_persists_after_scale(lb_node_list_before_scale,
                                                                load_balancer)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_down_data, execute_policy=True)
        self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._assert_lb_nodes_before_scale_persists_after_scale(lb_node_list_before_scale,
                                                                load_balancer)

    @tags(speed='slow')
    def test_remove_existing_lbaas_in_launch_config(self):
        """
        Remove lbaas id in the launch config and verify a scale up after the update,
        resulted in servers not added to the older lbaas id
        """
        policy_up_data = {'change': self.sp_change}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
                                                        self.load_balancer_1)
        self._update_launch_config(group)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
        activeservers_after_scale = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt + self.sp_change)
        active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
        server_ip_list = self._get_ipv4_address_list_on_servers(active_servers_from_scale)
        node_list_on_lb = [node.address for node in self._get_node_list_from_lb(self.load_balancer_1)]
        self.assertTrue(all([server_ip not in node_list_on_lb for server_ip in server_ip_list]))

    @unittest.skip('AUTO-378')
    def test_negative_create_group_with_invalid_load_balancer(self):
        """
        Create group with a random number/lb from a differnt region as the load balancer id
        and verify the scaling group deletes the servers after trying to add loadbalancer.
        Also, when 25 nodes already exist on a lb
        """
        load_balancer_list = [00000, self.lb_other_region]
        for each_load_balancer in load_balancer_list:
            group = self._create_group_given_lbaas_id(each_load_balancer)
            self._wait_for_servers_to_be_deleted_when_lb_invalid(
                group.id, group.groupConfiguration.minEntities)
            self.assertEquals(len(self.get_servers_containing_given_name_on_tenant(group_id=group.id)),
                              0, msg='Servers created on the group before trying to add the '
                              'invalid load balancer were not deleted on group {0}'.format(group.id))

    def _create_group_given_lbaas_id(self, *lbaas_ids):
        """
        Given the args, creates a group with minentities > 0 and the given number of lbaas
        Note: The lbaas are excepted to be present on the account
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_load_balancers=self._create_lbaas_list(*lbaas_ids),
            gc_cooldown=0)
        group = create_group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group

    def _verify_lbs_on_group_have_servers_as_nodes(self, group_id, server_ids_list, *lbaas_ids):
        """
        Given the list of active server ids on the group, create a list of the
        ip address of the servers on the group,
        and compare it to the list of ip addresses got from a list node
        call for the lbaas id.
        Get list of port of lbaas on the group and compare to the list of
        port on the lbaas id.
        (note: the test ensures the port are distint during group creation,
        which escapes the case this function would fail for, which is if the
        loadbalancer had a node with the port on it already, and autoscale
        failed to add node to that same port, this will not fail. This was done
        to keep it simple.)
        """
        # call nova list server, filter by ID and create ip address list
        servers_address_list = self._get_ipv4_address_list_on_servers(
            server_ids_list)
        # call otter, list launch config, create list of ports
        port_list_from_group = self._get_ports_from_otter_launch_configs(
            group_id)
        # call list node for each lbaas, create list of Ips and ports
        ports_list = []
        for each_loadbalancer in lbaas_ids:
            get_nodes_on_lb = self._get_node_list_from_lb(each_loadbalancer)
            nodes_list_on_lb = []
            for each_node in get_nodes_on_lb:
                nodes_list_on_lb.append(each_node.address)
                ports_list.append(each_node.port)
            # compare ip address lists and port lists
            for each_address in servers_address_list:
                self.assertTrue(each_address in nodes_list_on_lb)
        for each_port in port_list_from_group:
            self.assertTrue(each_port in ports_list)

    def _update_launch_config(self, group, *lbaas_ids):
        """
        Update the launch config to update to the given load balancer ids
        """
        if lbaas_ids:
            lbaas_list = self._create_lbaas_list(*lbaas_ids)
        else:
            lbaas_list = []
        update_lc_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=group.launchConfiguration.server.name,
            image_ref=group.launchConfiguration.server.imageRef,
            flavor_ref=group.launchConfiguration.server.flavorRef,
            personality=None,
            metadata=None,
            disk_config=None,
            networks=None,
            load_balancers=lbaas_list)
        self.assertEquals(update_lc_response.status_code, 204,
                          msg='Update launch config with load balancer failed for group '
                          '{0} with {1}'.format(group.id, update_lc_response.status_code))

    def _create_lbaas_list(self, *lbaas_ids):
        """
        Create a payload with lbaas id
        """
        lbaas_list = []
        if len(lbaas_ids):
            for each_lbaas_id in lbaas_ids:
                lbaas = {'loadBalancerId': each_lbaas_id,
                         'port': random.randint(1000, 9999)}
                lbaas_list.append(lbaas)
        return lbaas_list

    def _get_ipv4_address_list_on_servers(self, server_ids_list):
        """
        Returns the list of ipv4 addresses for the given list of servers
        """
        network_list = []
        for each_server in server_ids_list:
            network = (self.server_client.list_addresses(each_server).entity)
            for each_network in network.private.addresses:
                if str(each_network.version) is '4':
                    network_list.append(
                        each_network.addr)
        return network_list

    def _get_ports_from_otter_launch_configs(self, group_id):
        """
        Returns the list of ports in the luanch configs of the group_id
        """
        port_list = []
        launch_config = (
            self.autoscale_client.view_launch_config(group_id)).entity
        for each_lb in launch_config.loadBalancers:
            port_list.append(each_lb.port)
        return port_list

    def _get_node_list_from_lb(self, load_balancer_id):
        """
        Returns the list of nodes on the load balancer
        """
        return self.lbaas_client.list_nodes(load_balancer_id).entity

    def _assert_lb_nodes_before_scale_persists_after_scale(self, lb_node_list_before_any_operation,
                                                           load_balancer_id):
        """
        Gets the current list of lb nodes address and asserts that provided node
        address list (which is before any scale operation) still exists within the
        current list of lb node addresses
        """
        current_lb_node_list = [each_node.address for each_node in
                                self._get_node_list_from_lb(load_balancer_id)]
        self.assertTrue(set(lb_node_list_before_any_operation).issubset(set(current_lb_node_list)),
                        msg='nodes {0} is not a subset of {1}'.format(set(
                            lb_node_list_before_any_operation),
                            set(current_lb_node_list)))

    def _wait_for_servers_to_be_deleted_when_lb_invalid(self, group_id,
                                                        servers_before_lb, server_after_lb=0):
        """
        waits for servers_before_lb number of servers to be the desired capacity,
        then waits for the desired capacity to be server_after_lb when a group with an
        invalid load balancer is created.
        """
        end_time = time.time() + 600
        group_state = (self.autoscale_client.list_status_entities_sgroups(
            group_id)).entity
        if group_state.desiredCapacity is servers_before_lb:
            while time.time() < end_time:
                time.sleep(10)
                group_state = (self.autoscale_client.list_status_entities_sgroups(
                    group_id)).entity
                if group_state.desiredCapacity is server_after_lb:
                    return
            else:
                self.fail('Servers not deleted from group even when group has invalid'
                          ' load balancers!')
        else:
            self.fail('Number of servers building on the group are not as expected')
