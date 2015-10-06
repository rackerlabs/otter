"""
System Integration tests autoscaling with lbaas
"""

import random

from cafe.drivers.unittest.decorators import tags

from test_repo.autoscale.fixtures import AutoscaleFixture

from test_repo.autoscale.system.integration import common


class AutoscaleLbaasFixture(AutoscaleFixture):

    """
    System tests to verify lbaas integration with autoscale
    """
    @classmethod
    def setUpClass(cls):
        """
        Create 3 load balancers
        """
        super(AutoscaleLbaasFixture, cls).setUpClass()
        cls.common = common.CommonTestUtilities(cls.server_client,
                                                cls.autoscale_client,
                                                cls.lbaas_client)

        cls.load_balancer_1_response = cls.lbaas_client.create_load_balancer(
            'test', [], 'HTTP', 80, "PUBLIC")
        cls.load_balancer_1 = cls.load_balancer_1_response.entity.id
        cls.resources.add(cls.load_balancer_1,
                          cls.lbaas_client.delete_load_balancer)
        cls.load_balancer_2_response = cls.lbaas_client.create_load_balancer(
            'test', [], 'HTTP', 80, "PUBLIC")
        cls.load_balancer_2 = cls.load_balancer_2_response.entity.id
        cls.resources.add(cls.load_balancer_2,
                          cls.lbaas_client.delete_load_balancer)
        cls.load_balancer_3_response = cls.lbaas_client.create_load_balancer(
            'test', [], 'HTTP', 80, "PUBLIC")
        cls.load_balancer_3 = cls.load_balancer_3_response.entity.id
        cls.resources.add(cls.load_balancer_3,
                          cls.lbaas_client.delete_load_balancer)
        cls.lb_other_region = 0000

    @tags(speed='slow', type='lbaas', convergence='never')
    # Convergence: This doesn't work because Convergence just puts the group
    # into ERROR, because when the load balancer is deleted, it notices the LB
    # nodes are gone, and then tries to recreate the LB node for all active
    # servers. This is done simultaneously with deleting one server during the
    # scale-down in this test, but that doesn't matter much, because the failed
    # "add node" operation causes the entire convergence to fail.
    def test_delete_server_if_deleted_load_balancer_during_scale_down(self):
        """
        Create a load balancer and provide it in the launch config during
        create group.  Scale up, Delete the load balancer and scale down.
        Verify that the servers are scaled down even when the load balancer was
        deleted.
        """
        lb = self.lbaas_client.create_load_balancer('test', [], 'HTTP', 80,
                                                    "PUBLIC")
        lb_id = lb.entity.id
        policy_up_data = {'change': self.gc_min_entities_alt}
        policy_down_data = {'change': -self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(lb_id)
        self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self.autoscale_behaviors.create_policy_webhook(group.id,
                                                       policy_up_data,
                                                       execute_policy=True)
        servers_after_scale_up = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt * 2))
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, servers_after_scale_up, lb_id)
        self.successfully_delete_given_loadbalancer(lb_id)
        self.autoscale_behaviors.create_policy_webhook(group.id,
                                                       policy_down_data,
                                                       execute_policy=True)
        remaining_servers = self.wait_for_expected_number_of_active_servers(
            group.id, self.gc_min_entities_alt)
        actual_remaining_servers = self.assert_servers_deleted_successfully(
            group.launchConfiguration.server.name, 1)
        self.assertEquals(actual_remaining_servers, remaining_servers)

    @tags(speed='slow', type='lbaas', convergence='never')
    # Convergence: Convergence does not delete servers when they can't be added
    # to the LB: it just puts the group into ERROR and it's up to the user to
    # recreate the LB.
    def test_delete_server_if_deleted_load_balancer_during_scale_up(self):
        """
        Create a load balancer and provide it in the launch config during
        create group.  Delete the load balancer and scale up.  Verify that a
        new server for the scale up policy begin building, but is deleted after
        it is active, as the lb no longer exists.
        """
        lb = self.lbaas_client.create_load_balancer('test', [], 'HTTP', 80,
                                                    "PUBLIC")
        lb_id = lb.entity.id
        policy_up_data = {'change': self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(lb_id, server_building="3")
        servers_on_create_group = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt)
        )
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, servers_on_create_group, lb_id)
        self.successfully_delete_given_loadbalancer(lb_id)
        self.autoscale_behaviors.create_policy_webhook(group.id,
                                                       policy_up_data,
                                                       execute_policy=True)
        self.check_for_expected_number_of_building_servers(
            group.id, self.gc_min_entities_alt * 2)
        self.assert_servers_deleted_successfully(
            group.launchConfiguration.server.name,
            self.gc_min_entities_alt)

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_add_multiple_lbaas_to_group(self):
        """
        Adding multiple load balancers within the launch config when creating
        the group, cause the servers to be added as nodes to all the load
        balancers
        """
        group = self._create_group_given_lbaas_id(self.load_balancer_1,
                                                  self.load_balancer_2,
                                                  self.load_balancer_3)
        active_server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id,
            active_server_list, self.load_balancer_1, self.load_balancer_2,
            self.load_balancer_3)

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_update_launch_config_to_include_multiple_lbaas(self):
        """
        Updating the launch config to add multiple load balancer to a group
        that had only one load balancer, results in the new servers of that
        group to be added as nodes to all the load balancers
        """
        policy_data = {'change': self.sp_change}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, active_server_list, self.load_balancer_1)
        self._update_launch_config(group, self.load_balancer_1,
                                   self.load_balancer_2, self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_data,
                                                       execute_policy=True)
        activeservers_after_scale = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt + self.sp_change)
        )
        active_servers_from_scale = (set(activeservers_after_scale)
                                     - set(active_server_list))
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id,
            active_servers_from_scale, self.load_balancer_1,
            self.load_balancer_2, self.load_balancer_3)

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_update_launch_config_to_include_lbaas(self):
        """
        Update the launch config to add a load balancer to a group that did not
        have a load balancer, results in the new servers of that group to be
        added as nodes to the load balancers
        """
        policy_data = {'change': self.sp_change}
        group = (self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            network_type='public')).entity
        self.resources.add(group, self.empty_scaling_group)
        active_server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._update_launch_config(group, self.load_balancer_1,
                                   self.load_balancer_2, self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(group.id, policy_data,
                                                       execute_policy=True)
        activeservers_after_scale = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt + self.sp_change)
        )
        active_servers_from_scale = (set(activeservers_after_scale)
                                     - set(active_server_list))
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id,
            active_servers_from_scale, self.load_balancer_1,
            self.load_balancer_2, self.load_balancer_3)

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_update_existing_lbaas_in_launch_config(self):
        """
        Create a scaling group with a given load balancer and verify the
        servers on the scaling group are added as nodes on the load balancer.

        Update the group's launch config to a different loadbalancer scale up
        and verify that the new servers are added to the newly update
        loadbalancer.

        Scale down and verify that servers with the older launch config are
        deleted i.e. the load balancer added during group creation no longer
        has the nodes from the scaling group.
        """
        policy_up_data = {'change': self.gc_min_entities_alt}
        policy_down_data = {'change': -self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id,
            active_server_list, self.load_balancer_1)
        self._update_launch_config(group, self.load_balancer_2)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_up_data, execute_policy=True)
        activeservers_after_scale = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt * 2))
        active_servers_from_scale = (set(activeservers_after_scale)
                                     - set(active_server_list))
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, active_servers_from_scale, self.load_balancer_2)
        scaled_down_server_ip = self.common.get_ipv4_address_list_on_servers(
            active_server_list)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_down_data, execute_policy=True)
        activeservers_scaledown = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt))
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, activeservers_scaledown, self.load_balancer_2)
        lb_node_list = [each_node.address for each_node
                        in self._get_node_list_from_lb(
                            self.load_balancer_1)]
        self.assertTrue(set(scaled_down_server_ip) not in set(lb_node_list))

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_existing_nodes_on_lb_unaffected_by_scaling(self):
        """
        Get load balancer node id list before anyscale operation, create a
        scaling group with minentities>1, scale up and then scale down.  After
        each scale operation, verify the nodes existing on the load balancer
        before any scale operation persists
        """
        load_balancer = self.load_balancer_1
        lb_node_list_before_scale = [
            each_node.address for each_node in
            self._get_node_list_from_lb(load_balancer)
        ]
        policy_up_data = {'change': self.gc_min_entities_alt}
        policy_down_data = {'change': -self.gc_min_entities_alt}
        group = self._create_group_given_lbaas_id(load_balancer)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_up_data, execute_policy=True)
        self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt * 2)
        self._assert_lb_nodes_before_scale_persists_after_scale(
            lb_node_list_before_scale, load_balancer)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_down_data, execute_policy=True)
        self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._assert_lb_nodes_before_scale_persists_after_scale(
            lb_node_list_before_scale, load_balancer
        )

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_remove_existing_lbaas_in_launch_config(self):
        """
        Remove lbaas id in the launch config and verify a scale up after the
        update, resulted in servers not added to the older lbaas id
        """
        policy_up_data = {'change': self.sp_change}
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        active_server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, active_server_list,
            self.load_balancer_1)
        self._update_launch_config(group)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_up_data, execute_policy=True)
        activeservers_after_scale = (
            self.wait_for_expected_number_of_active_servers(
                group.id, self.gc_min_entities_alt + self.sp_change))
        active_servers_from_scale = (set(activeservers_after_scale)
                                     - set(active_server_list))
        server_ip_list = self.common.get_ipv4_address_list_on_servers(
            active_servers_from_scale)
        node_list_on_lb = [node.address for node in
                           self._get_node_list_from_lb(self.load_balancer_1)]
        self.assertTrue(all([server_ip not in node_list_on_lb
                             for server_ip in server_ip_list]))

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_force_delete_group_with_load_balancer(self):
        """
        Force delete a scaling group with active servers and load balancer,
        deletes the servers and the modes form the load balancer and then
        deletes the group.
        """
        group = self._create_group_given_lbaas_id(self.load_balancer_1)
        self.verify_group_state(group.id, self.gc_min_entities_alt)
        server_list = self.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        server_ip_list = self.common.get_ipv4_address_list_on_servers(
            server_list)
        delete_group_response = self.autoscale_client.delete_scaling_group(
            group.id, 'true')
        self.assertEquals(
            delete_group_response.status_code, 204,
            msg='Could not force delete group {0} when active servers existed '
            'on it '.format(group.id))
        self.assert_servers_deleted_successfully(
            group.launchConfiguration.server.name)
        node_list_on_lb = [node.address for node in
                           self._get_node_list_from_lb(self.load_balancer_1)]
        self.assertTrue(all([server_ip not in node_list_on_lb for server_ip
                             in server_ip_list]))

    @tags(speed='slow', type='lbaas', convergence='never')
    # Convergence: Convergence does not delete servers when they can't be added
    # to the LB: it just puts the group into ERROR and it's up to the user to
    # recreate the LB.
    def test_negative_create_group_with_invalid_load_balancer(self):
        """
        Create group with a random number/lb from a differnt region as the load
        balancer id and verify the scaling group deletes the servers after
        trying to add loadbalancer.  Also, when 25 nodes already exist on a lb
        """
        load_balancer_list = [self.lb_other_region]
        for each_load_balancer in load_balancer_list:
            group = self._create_group_given_lbaas_id(each_load_balancer,
                                                      server_building="3")
            self._wait_for_servers_to_be_deleted_when_lb_invalid(
                group.id, group.groupConfiguration.minEntities)
            self.assert_servers_deleted_successfully(
                group.launchConfiguration.server.name)

    @tags(speed='slow', type='lbaas', convergence='yes')
    def test_load_balancer_pending_update_or_error_state(self):
        """
        Ensure all the servers are created and added to the load balancer and
        then deleted and node removed from the load balancer when scale down to
        desired capacity 1.

        Note: Mimic has load_balancer_3 set as the load balancer that returns
        pending update state less than 10 times.
        """
        policy_up_data = {'desired_capacity': 10}
        policy_down_data = {'desired_capacity': 1}
        group = self._create_group_given_lbaas_id(self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_up_data, execute_policy=True)
        activeservers_after_scale_up = (
            self.wait_for_expected_number_of_active_servers(
                group.id, policy_up_data['desired_capacity']))
        ip_list_on_scale_up = self.common.get_ipv4_address_list_on_servers(
            activeservers_after_scale_up)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, activeservers_after_scale_up, self.load_balancer_3)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, policy_down_data, execute_policy=True)
        activeservers_after_scaledown = (
            self.wait_for_expected_number_of_active_servers(
                group.id, policy_down_data['desired_capacity']))
        ip_list_on_scale_down = self.common.get_ipv4_address_list_on_servers(
            activeservers_after_scaledown)
        self.common.verify_lbs_on_group_have_servers_as_nodes(
            self, group.id, activeservers_after_scaledown, self.load_balancer_3
        )
        ips_removed = set(ip_list_on_scale_up) - set(ip_list_on_scale_down)
        self._verify_given_ips_do_not_exist_as_nodes_on_lb(
            self.load_balancer_3, ips_removed)
        self.assert_servers_deleted_successfully(
            group.launchConfiguration.server.name,
            self.gc_min_entities_alt)

    @tags(speed='slow', type='lbaas', convergence='never')
    # Convergence: Convergence does not delete servers when they can't be added
    # to the LB: it just puts the group into ERROR and it's up to the user to
    # recreate the LB.
    def test_group_with_invalid_load_balancer_among_multiple_load_balancers(
            self):
        """
        Create a group with one invalid load balancer among multiple load
        balancers, and verify that all the servers on the group are deleted and
        nodes from valid load balancers are removed.
        """
        group = self._create_group_given_lbaas_id(self.load_balancer_3,
                                                  self.lb_other_region)
        self.wait_for_expected_group_state(group.id, 0, 900)
        nodes_on_lb = self._get_node_list_from_lb(self.load_balancer_3)
        self.assertEquals(len(nodes_on_lb), 0)

    def _create_group_given_lbaas_id(self, *lbaas_ids, **kwargs):
        """
        Given the args, creates a group with minentities > 0 and the given
        number of lbaas Note: The lbaas are excepted to be present on the
        account

        Any kwargs passed are used as the metadata for the server being built.
        """
        create_group_response = (
            self.autoscale_behaviors.create_scaling_group_given(
                gc_min_entities=self.gc_min_entities_alt,
                lc_load_balancers=self._create_lbaas_list(*lbaas_ids),
                gc_cooldown=0, network_type='public',
                lc_metadata=kwargs)
        )
        group = create_group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group

    def _verify_given_ips_do_not_exist_as_nodes_on_lb(self, lbaas_id, ip_list):
        """
        Waits for nodes in the ip_list to be deleted from the given load
        balancer
        """
        def verify(elapsed_time):
            lb_node_list = [each_node.address for each_node in
                            self._get_node_list_from_lb(lbaas_id)]
            if not set(lb_node_list).isdisjoint(ip_list):
                self.fail(
                    "waited {0} seconds for nodes {1} to be deleted from load"
                    "balancer {2} but {3} exist".format(
                        elapsed_time, ip_list, lbaas_id, lb_node_list))

        return self.autoscale_behaviors.retry(
            verify, timeout=600, interval_time=10)

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
        self.assertEquals(
            update_lc_response.status_code, 204,
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

    def _get_node_list_from_lb(self, load_balancer_id):
        """
        Returns the list of nodes on the load balancer
        """
        return self.lbaas_client.list_nodes(load_balancer_id).entity

    def _assert_lb_nodes_before_scale_persists_after_scale(
            self, lb_node_list_before_any_operation, load_balancer_id):
        """
        Gets the current list of lb nodes address and asserts that provided
        node address list (which is before any scale operation) still exists
        within the current list of lb node addresses
        """
        current_lb_node_list = [each_node.address for each_node in
                                self._get_node_list_from_lb(load_balancer_id)]
        self.assertTrue(
            set(lb_node_list_before_any_operation).issubset(
                set(current_lb_node_list)),
            msg='nodes {0} is not a subset of {1}'.format(
                set(lb_node_list_before_any_operation),
                set(current_lb_node_list)))

    def _wait_for_servers_to_be_deleted_when_lb_invalid(
            self, group_id, servers_before_lb, server_after_lb=0):
        """
        waits for servers_before_lb number of servers to be the desired
        capacity, then waits for the desired capacity to be server_after_lb
        when a group with an invalid load balancer is created.
        """
        group_state = (self.autoscale_client.list_status_entities_sgroups(
            group_id)).entity
        if group_state.desiredCapacity is servers_before_lb:
            def wait_for_servers(elapsed_time):
                group_state = (
                    self.autoscale_client.list_status_entities_sgroups(
                        group_id)).entity
                if group_state.desiredCapacity != server_after_lb:
                    self.fail(
                        'Servers not deleted from group even when group has '
                        'invalid load balancers!')

            return self.autoscale_behaviors.retry(
                wait_for_servers, timeout=600, interval_time=10)
        else:
            self.fail(
                'Number of servers building on the group are not as expected')
