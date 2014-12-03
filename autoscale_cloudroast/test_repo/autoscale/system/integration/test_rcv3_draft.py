"""
System Integration tests for autoscaling with RackConnect V3 load balancers
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags
#import random
#import time
from cloudcafe.common.tools.datagen import rand_name


class AutoscaleRackConnectFixture(AutoscaleFixture):

    """
    System tests to verify lbaas integration with autoscale
    """
    #@classmethod
    def setUp(self):
        """
        Capture the initial state of the shared load balancer pools
        """

        super(AutoscaleRackConnectFixture, self).setUp()
        # Get list of available pools
        self.pool_1 = None
        self.pool_2 = None
        tenant_pools = self._get_available_pools()
        # Since RCV3 pools must be created by human intervention,
        # verify that at least one exists before proceeding with tests
        if len(tenant_pools) == 0:
            raise Exception("NoLBPoolsError")
        else:
            print tenant_pools
            print "lb 1 : {}".format(self.rc_load_balancer_pool_1)
            if self.rc_load_balancer_pool_1['type'] == 'mimic':
                # Mimic should have a single pool out of the box
                self.pool_1 = tenant_pools[0]
                try:
                    # Create a second pool for advanced testing TODO
                    self.pool_2 = tenant_pools[1]
                except:
                    print "Error: No second RCV3 pool configured in Mimic"
            else:   # Check that the pool in the config exists
                for pool in tenant_pools:
                    if pool.id == self.rc_load_balancer_pool_1['loadBalancerId']:
                        self.pool_1 = pool
                    if pool.id == self.rc_load_balancer_pool_2['loadBalancerId']:
                        self.pool_2 = pool

        # if type of rc_load_balancer_pool_1 is mimic, use the first available pool as pool 1
        # else if pool from config is in list, use as pool 1, if not abort
        # same for pool 2

        # cls.load_balancer_1_response = cls.lbaas_client.create_load_balancer('test', [],
        #                                                                      'HTTP', 80, "PUBLIC")
        # cls.load_balancer_1 = cls.load_balancer_1_response.entity.id
        # cls.resources.add(cls.load_balancer_1, cls.lbaas_client.delete_load_balancer)
        # cls.load_balancer_2_response = cls.lbaas_client.create_load_balancer('test', [],
        #                                                                      'HTTP', 80, "PUBLIC")
        # cls.load_balancer_2 = cls.load_balancer_2_response.entity.id
        # cls.resources.add(cls.load_balancer_2, cls.lbaas_client.delete_load_balancer)
        # cls.load_balancer_3_response = cls.lbaas_client.create_load_balancer('test', [],
        #                                                                      'HTTP', 80, "PUBLIC")
        # cls.load_balancer_3 = cls.load_balancer_3_response.entity.id
        # cls.resources.add(cls.load_balancer_3, cls.lbaas_client.delete_load_balancer)
        # cls.lb_other_region = 0000
        print "Get initial state of LB Pools ------------------------------------- "

    @tags(speed='slow', type='rcv3')
    def test_always_pass(self):
        """
        Create a test that always passes
        """
        print "This should pass"
        #print "Existing LB 1 -- %s".format(self.rc_load_balancer_pool_1)
        self.assertTrue(True)

    @tags(speed='slow', type='rcv3')
    def test_create_scaling_group_with_pool(self):
        """
        Test that it is possible to create a scaling group with 0 entities
        connected to an RCV3 LB pool
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool_1.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools, group_min=0)

        pool_group = pool_group_resp.entity
        print pool_group
        self.resources.add(pool_group.id,
                           self.autoscale_client.delete_scaling_group_with_force)

        self.assertTrue(pool_group_resp.ok,
                        msg='Create scaling group call failed with API Response: {0} for '
                        'group {1}'.format(pool_group_resp.content, pool_group.id))
        self.assertEquals(self.create_resp.status_code, 201,
                          msg='The create failed with {0} for group '
                          '{1}'.format(pool_group_resp.status_code, pool_group.id))
        self.assertEquals(pool_group.launchConfiguration.loadBalancers[0].loadBalancerId,
                          self.pool_1.id,
                          msg='The launchConfig for group {0} did not contain the load balancer'
                          .format(pool_group.id))
        self.assertEquals(pool_group.launchConfiguration.loadBalancers[0].type, "RackConnectV3",
                          msg='Load balancer type {0} is not correct for RackConnect pools'
                          .format(pool_group.launchConfiguration.loadBalancers[0].type))

    @tags(speed='slow', type='rcv3')
    def test_create_scaling_group_with_pool_default_1(self):
        """
        Test that it is possible to create a scaling group with 0 entities
        connected to an RCV3 LB pool
        """
        # Create a scaling group with zero servers
        lb_pools = [{'loadBalancerId': self.pool_1.id, 'type': 'RackConnectV3'}]
        pool_group_resp = self._create_rcv3_group(lb_list=lb_pools, group_min=1)

        pool_group = pool_group_resp.entity
        print pool_group
        self.resources.add(pool_group.id,
                           self.autoscale_client.delete_scaling_group_with_force)

        # Wait for an active server according to autoscale
        self.wait_for_expected_number_of_active_servers(pool_group.id, 1, timeout=600)

        # Check that there is a server on the LB_Pools
        init_cloud_servers = self.pool_1.node_counts['cloud_servers']
        new_counts = self._get_node_counts_on_pool(self.pool_1.id)
        print new_counts
        expected_count = init_cloud_servers + 1

        self.assertEqual(new_counts['cloud_servers'], expected_count, msg=' count {0}'
                         ' is not equal to initial count [{1}] + 1'.format(new_counts['cloud_servers'],
                                                                           init_cloud_servers))

    def _get_available_pools(self):
        """
        List the rcv3 pools on the tenant
        """
        pools = self.rcv3_client.list_pools().entity.pools
        return pools

    def _get_node_counts_on_pool(self, pool_id):
        """
        Get the node counts on a given pool
        """
        pool_list = self._get_available_pools()
        for pool in pool_list:
            print pool
            if pool.id == pool_id:
                return pool.node_counts

    # def _get_node_list_from_rc(self, pool_id):
    #     """
    #     Returns the list of nodes on the load balancer pool
    #     """
    #     return self.rcv3_client.list_nodes(pool_id).entity

    def _create_rcv3_group(self, lb_list=None, group_min=None,
                           net1='00000000-0000-0000-0000-000000000000',
                           net2='11111111-1111-1111-1111-111111111111'):
        """
        Create a scaling group
        """
        if group_min is None:
            group_min = self.gc_min_entities
        self.gc_name = rand_name('rcv3_test_group')
        self.gc_max_entities = 10
        self.gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                            'gc_meta_key_2': 'gc_meta_value_2'}
        # self.file_contents = 'This is a test file.'
        # self.lc_personality = [{'path': '/root/.csivh',
        #                         'contents': base64.b64encode(self.file_contents)}]
        self.lc_metadata = {'meta_key_1': 'meta_value_1',
                            'meta_key_2': 'meta_value_2'}
        self.lc_disk_config = 'AUTO'
        # self.lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'},
        #                     {'uuid': '00000000-0000-0000-0000-000000000000'}]
        self.lc_networks = [{'uuid': net1}, {'uuid': net2}]
        #self.lc_load_balancers = [{'loadBalancerId': 9099, 'port': 8080}]
        # self.lc_load_balancers = [{'loadBalancerId': "364b6c45-914d-422f-be30-3d18d612ecf4",
        #                            'type': 'RackConnectV3'}]

        self.sp_list = [{
            'name': 'scale up by 1',
            'change': 1,
            'cooldown': 0,
            'type': 'webhook'
        }]
        #self.lc_block_device_mapping = block_device_mapping
        # Create a scaling group with zero servers
        self.create_resp = self.autoscale_client.create_scaling_group(
            gc_name=self.gc_name,
            gc_cooldown=self.gc_cooldown,
            gc_min_entities=group_min,
            #gc_min_entities=self.gc_min_entities,
            gc_max_entities=self.gc_max_entities,
            gc_metadata=self.gc_metadata,
            lc_name=self.lc_name,
            lc_image_ref=self.lc_image_ref,
            lc_flavor_ref=self.lc_flavor_ref,
            # lc_personality=self.lc_personality,
            lc_metadata=self.lc_metadata,
            lc_disk_config=self.lc_disk_config,
            lc_networks=self.lc_networks,
            #lc_block_device_mapping=block_device_mapping,
            lc_load_balancers=lb_list,
            sp_list=self.sp_list)
            #network_type='public')
        return self.create_resp

    # @tags(speed='slow', type='lbaas')
    # def test_delete_server_if_deleted_load_balancer_during_scale_up(self):
    #     """
    #     Create a load balancer and provide it in the launch config during create group.
    #     Delete the load balancer and scale up. Verify that a new server for the scale up
    #     policy begin building, but is deleted after it is active, as the lb no longer exists.
    #     """
    #     lb = self.lbaas_client.create_load_balancer('test', [], 'HTTP', 80, "PUBLIC")
    #     lb_id = lb.entity.id
    #     policy_up_data = {'change': self.gc_min_entities_alt}
    #     group = self._create_group_given_lbaas_id(lb_id, server_building="3")
    #     servers_on_create_group = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, servers_on_create_group, lb_id)
    #     self.successfully_delete_given_loadbalancer(lb_id)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
    #     self.check_for_expected_number_of_building_servers(group.id, self.gc_min_entities_alt * 2)
    #     self.assert_servers_deleted_successfully(group.launchConfiguration.server.name,
    #                                              self.gc_min_entities_alt)

    # @tags(speed='slow', type='lbaas')
    # def test_add_multiple_lbaas_to_group(self):
    #     """
    #     Adding multiple load balancers within the launch config when creating the group,
    #     cause the servers to be added as nodes to all the load balancers
    #     """
    #     group = self._create_group_given_lbaas_id(self.load_balancer_1,
    #                                               self.load_balancer_2, self.load_balancer_3)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
    #                                                     self.load_balancer_1,
    #                                                     self.load_balancer_2,
    #                                                     self.load_balancer_3)

    # @tags(speed='slow', type='lbaas')
    # def test_update_launch_config_to_include_multiple_lbaas(self):
    #     """
    #     Updating the launch config to add multiple load balancer to a group that had
    #     only one load balancer, results in the new servers of that group to be added
    #     as nodes to all the load balancers
    #     """
    #     policy_data = {'change': self.sp_change}
    #     group = self._create_group_given_lbaas_id(self.load_balancer_1)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
    #                                                     self.load_balancer_1)
    #     self._update_launch_config(group, self.load_balancer_1, self.load_balancer_2,
    #                                self.load_balancer_3)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_data, execute_policy=True)
    #     activeservers_after_scale = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt + self.sp_change)
    #     active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
    #                                                     self.load_balancer_1,
    #                                                     self.load_balancer_2,
    #                                                     self.load_balancer_3)

    # @tags(speed='slow', type='lbaas')
    # def test_update_launch_config_to_include_lbaas(self):
    #     """
    #     Update the launch config to add a load balancer to a group that did not
    #     have a load balancer, results in the new servers of that group to be added
    #     as nodes to the load balancers
    #     """
    #     policy_data = {'change': self.sp_change}
    #     group = (self.autoscale_behaviors.create_scaling_group_given(
    #         gc_min_entities=self.gc_min_entities_alt,
    #         network_type='public')).entity
    #     self.resources.add(group, self.empty_scaling_group)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._update_launch_config(group, self.load_balancer_1, self.load_balancer_2,
    #                                self.load_balancer_3)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_data, execute_policy=True)
    #     activeservers_after_scale = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt + self.sp_change)
    #     active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
    #                                                     self.load_balancer_1,
    #                                                     self.load_balancer_2,
    #                                                     self.load_balancer_3)

    # @tags(speed='slow', type='lbaas')
    # def test_update_existing_lbaas_in_launch_config(self):
    #     """
    #     Create a scaling group with a given load balancer and verify the servers on the scaling group
    #     are added as nodes on the load balancer.
    #     Update the group's launch config to a different loadbalancer scale up and verify that the new
    #     servers are added to the newly update loadbalancer.
    #     Scale down and verify that servers with the older launch config are deleted i.e. the load
    #     balancer added during group creation no longer has the nodes from the scaling group.
    #     """
    #     policy_up_data = {'change': self.gc_min_entities_alt}
    #     policy_down_data = {'change': -self.gc_min_entities_alt}
    #     group = self._create_group_given_lbaas_id(self.load_balancer_1)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
    #                                                     self.load_balancer_1)
    #     self._update_launch_config(group, self.load_balancer_2)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
    #     activeservers_after_scale = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt * 2)
    #     active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_servers_from_scale,
    #                                                     self.load_balancer_2)
    #     scaled_down_server_ip = self._get_ipv4_address_list_on_servers(active_server_list)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_down_data, execute_policy=True)
    #     activeservers_scaledown = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, activeservers_scaledown,
    #                                                     self.load_balancer_2)
    #     lb_node_list = [each_node.address for each_node in self._get_node_list_from_lb(
    #         self.load_balancer_1)]
    #     self.assertTrue(set(scaled_down_server_ip) not in set(lb_node_list))

    # @tags(speed='slow', type='lbaas')
    # def test_delete_group_when_autoscale_server_is_the_last_node_on_lb(self):
    #     """
    #     Create a scaling group with load balancer. After the servers on the group are added to
    #     the loadbalancer, delete the older node with which the lb was created. Update minentities
    #     on the group to scale down and delete group.
    #     """
    #     load_balancer = self.load_balancer_3
    #     lb_node_id_list_before_scale = [each_node.id for each_node in self._get_node_list_from_lb(
    #         load_balancer)]
    #     group = self._create_group_given_lbaas_id(load_balancer)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
    #                                                     load_balancer)
    #     self.delete_nodes_in_loadbalancer(lb_node_id_list_before_scale, load_balancer)
    #     self.empty_scaling_group(group=group, delete=False)
    #     self.assert_servers_deleted_successfully(group.launchConfiguration.server.name)
    #     lb_node_after_del = self._get_node_list_from_lb(load_balancer)
    #     self.assertEquals(len(lb_node_after_del), 0)

    # @tags(speed='slow', type='lbaas')
    # def test_existing_nodes_on_lb_unaffected_by_scaling(self):
    #     """
    #     Get load balancer node id list before anyscale operation, create a scaling group
    #     with minentities>1, scale up and then scale down. After each scale operation,
    #     verify the nodes existing on the load balancer before any scale operation persists
    #     """
    #     load_balancer = self.load_balancer_1
    #     lb_node_list_before_scale = [each_node.address for each_node in
    #                                  self._get_node_list_from_lb(load_balancer)]
    #     policy_up_data = {'change': self.gc_min_entities_alt}
    #     policy_down_data = {'change': -self.gc_min_entities_alt}
    #     group = self._create_group_given_lbaas_id(load_balancer)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
    #     self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt * 2)
    #     self._assert_lb_nodes_before_scale_persists_after_scale(lb_node_list_before_scale,
    #                                                             load_balancer)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_down_data, execute_policy=True)
    #     self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._assert_lb_nodes_before_scale_persists_after_scale(lb_node_list_before_scale,
    #                                                             load_balancer)

    # @tags(speed='slow', type='lbaas')
    # def test_remove_existing_lbaas_in_launch_config(self):
    #     """
    #     Remove lbaas id in the launch config and verify a scale up after the update,
    #     resulted in servers not added to the older lbaas id
    #     """
    #     policy_up_data = {'change': self.sp_change}
    #     group = self._create_group_given_lbaas_id(self.load_balancer_1)
    #     active_server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, active_server_list,
    #                                                     self.load_balancer_1)
    #     self._update_launch_config(group)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
    #     activeservers_after_scale = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt + self.sp_change)
    #     active_servers_from_scale = set(activeservers_after_scale) - set(active_server_list)
    #     server_ip_list = self._get_ipv4_address_list_on_servers(active_servers_from_scale)
    #     node_list_on_lb = [node.address for node in self._get_node_list_from_lb(self.load_balancer_1)]
    #     self.assertTrue(all([server_ip not in node_list_on_lb for server_ip in server_ip_list]))

    # @tags(speed='slow', type='lbaas')
    # def test_force_delete_group_with_load_balancer(self):
    #     """
    #     Force delete a scaling group with active servers and load balancer, deletes the servers and the
    #     modes form the load balancer and then deletes the group.
    #     """
    #     group = self._create_group_given_lbaas_id(self.load_balancer_1)
    #     self.verify_group_state(group.id, self.gc_min_entities_alt)
    #     server_list = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         self.gc_min_entities_alt)
    #     server_ip_list = self._get_ipv4_address_list_on_servers(server_list)
    #     delete_group_response = self.autoscale_client.delete_scaling_group(group.id, 'true')
    #     self.assertEquals(delete_group_response.status_code, 204,
    #                       msg='Could not force delete group {0} when active servers existed '
    #                       'on it '.format(group.id))
    #     self.assert_servers_deleted_successfully(group.launchConfiguration.server.name)
    #     node_list_on_lb = [node.address for node in self._get_node_list_from_lb(self.load_balancer_1)]
    #     self.assertTrue(all([server_ip not in node_list_on_lb for server_ip in server_ip_list]))

    # @tags(speed='slow', type='lbaas')
    # def test_negative_create_group_with_invalid_load_balancer(self):
    #     """
    #     Create group with a random number/lb from a differnt region as the load balancer id
    #     and verify the scaling group deletes the servers after trying to add loadbalancer.
    #     Also, when 25 nodes already exist on a lb
    #     """
    #     load_balancer_list = [self.lb_other_region]
    #     for each_load_balancer in load_balancer_list:
    #         group = self._create_group_given_lbaas_id(each_load_balancer)
    #         self._wait_for_servers_to_be_deleted_when_lb_invalid(
    #             group.id, group.groupConfiguration.minEntities)
    #         self.assert_servers_deleted_successfully(group.launchConfiguration.server.name)

    # @tags(speed='slow', type='lbaas')
    # def test_load_balancer_pending_update_or_error_state(self):
    #     """
    #     Ensure all the servers are created and added to the load balancer and then deleted
    #     and node removed from the load balancer when scale down to desired capacity 1.
    #     Note: Mimic has load_balancer_3 set as the load balancer that returns pending update
    #     state less than 10 times.
    #     """
    #     policy_up_data = {'desired_capacity': 10}
    #     policy_down_data = {'desired_capacity': 1}
    #     group = self._create_group_given_lbaas_id(self.load_balancer_3)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_up_data, execute_policy=True)
    #     activeservers_after_scale_up = self.wait_for_expected_number_of_active_servers(
    #         group.id, policy_up_data['desired_capacity'])
    #     ip_list_on_scale_up = self._get_ipv4_address_list_on_servers(activeservers_after_scale_up)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, activeservers_after_scale_up,
    #                                                     self.load_balancer_3)
    #     self.autoscale_behaviors.create_policy_webhook(group.id, policy_down_data, execute_policy=True)
    #     activeservers_after_scaledown = self.wait_for_expected_number_of_active_servers(
    #         group.id,
    #         policy_down_data['desired_capacity'])
    #     ip_list_on_scale_down = self._get_ipv4_address_list_on_servers(activeservers_after_scaledown)
    #     self._verify_lbs_on_group_have_servers_as_nodes(group.id, activeservers_after_scaledown,
    #                                                     self.load_balancer_3)
    #     ips_removed = set(ip_list_on_scale_up) - set(ip_list_on_scale_down)
    #     self._verify_given_ips_do_not_exist_as_nodes_on_lb(self.load_balancer_3, ips_removed)
    #     self.assert_servers_deleted_successfully(
    #         group.launchConfiguration.server.name,
    #         self.gc_min_entities_alt)

    # @tags(speed='slow', type='lbaas')
    # def test_group_with_invalid_load_balancer_among_multiple_load_balancers(self):
    #     """
    #     Create a group with one invalid load balancer among multiple load balancers, and
    #     verify that all the servers on the group are deleted and nodes from valid load balancers
    #     are removed.
    #     """
    #     group = self._create_group_given_lbaas_id(self.load_balancer_3, self.lb_other_region)
    #     self.wait_for_expected_group_state(group.id, 0, 900)
    #     nodes_on_lb = self._get_node_list_from_lb(self.load_balancer_3)
    #     self.assertEquals(len(nodes_on_lb), 0)

    # def _create_group_given_lbaas_id(self, *lbaas_ids, **kwargs):
    #     """
    #     Given the args, creates a group with minentities > 0 and the given number of lbaas
    #     Note: The lbaas are excepted to be present on the account

    #     Any kwargs passed are used as the metadata for the server being built.
    #     """
    #     create_group_response = self.autoscale_behaviors.create_scaling_group_given(
    #         gc_min_entities=self.gc_min_entities_alt,
    #         lc_load_balancers=self._create_lbaas_list(*lbaas_ids),
    #         gc_cooldown=0, network_type='public',
    #         lc_metadata=kwargs)
    #     group = create_group_response.entity
    #     self.resources.add(group, self.empty_scaling_group)
    #     return group

    # def _verify_given_ips_do_not_exist_as_nodes_on_lb(self, lbaas_id, ip_list):
    #     """
    #     Waits for nodes in the ip_list to be deleted from the given load balancer
    #     """
    #     end_time = time.time() + 600
    #     while time.time() < end_time:
    #         lb_node_list = [each_node.address for each_node in self._get_node_list_from_lb(lbaas_id)]
    #         if set(lb_node_list).isdisjoint(ip_list):
    #             break
    #         time.sleep(10)
    #     else:
    #         self.fail("waited one minute for nodes {0} to be deleted from load"
    #                   "balancer {1} but {2} exist".format(ip_list, lbaas_id, lb_node_list))

    # def _verify_lbs_on_group_have_servers_as_nodes(self, group_id, server_ids_list, *lbaas_ids):
    #     """
    #     Given the list of active server ids on the group, create a list of the
    #     ip address of the servers on the group,
    #     and compare it to the list of ip addresses got from a list node
    #     call for the lbaas id.
    #     Get list of port of lbaas on the group and compare to the list of
    #     port on the lbaas id.
    #     (note: the test ensures the port are distint during group creation,
    #     which escapes the case this function would fail for, which is if the
    #     loadbalancer had a node with the port on it already, and autoscale
    #     failed to add node to that same port, this will not fail. This was done
    #     to keep it simple.)
    #     """
    #     # call nova list server, filter by ID and create ip address list
    #     servers_address_list = self._get_ipv4_address_list_on_servers(
    #         server_ids_list)
    #     # call otter, list launch config, create list of ports
    #     port_list_from_group = self._get_ports_from_otter_launch_configs(
    #         group_id)
    #     # call list node for each lbaas, create list of Ips and ports
    #     ports_list = []
    #     for each_loadbalancer in lbaas_ids:
    #         get_nodes_on_lb = self._get_node_list_from_lb(each_loadbalancer)
    #         nodes_list_on_lb = []
    #         for each_node in get_nodes_on_lb:
    #             nodes_list_on_lb.append(each_node.address)
    #             ports_list.append(each_node.port)
    #         # compare ip address lists and port lists
    #         for each_address in servers_address_list:
    #             self.assertTrue(each_address in nodes_list_on_lb)
    #     for each_port in port_list_from_group:
    #         self.assertTrue(each_port in ports_list)

    # def _update_launch_config(self, group, *lbaas_ids):
    #     """
    #     Update the launch config to update to the given load balancer ids
    #     """
    #     if lbaas_ids:
    #         lbaas_list = self._create_lbaas_list(*lbaas_ids)
    #     else:
    #         lbaas_list = []
    #     update_lc_response = self.autoscale_client.update_launch_config(
    #         group_id=group.id,
    #         name=group.launchConfiguration.server.name,
    #         image_ref=group.launchConfiguration.server.imageRef,
    #         flavor_ref=group.launchConfiguration.server.flavorRef,
    #         personality=None,
    #         metadata=None,
    #         disk_config=None,
    #         networks=None,
    #         load_balancers=lbaas_list)
    #     self.assertEquals(update_lc_response.status_code, 204,
    #                       msg='Update launch config with load balancer failed for group '
    #                       '{0} with {1}'.format(group.id, update_lc_response.status_code))

    # def _create_lbaas_list(self, *lbaas_ids):
    #     """
    #     Create a payload with lbaas id
    #     """
    #     lbaas_list = []
    #     if len(lbaas_ids):
    #         for each_lbaas_id in lbaas_ids:
    #             lbaas = {'loadBalancerId': each_lbaas_id,
    #                      'port': random.randint(1000, 9999)}
    #             lbaas_list.append(lbaas)
    #     return lbaas_list

    # def _get_ipv4_address_list_on_servers(self, server_ids_list):
    #     """
    #     Returns the list of ipv4 addresses for the given list of servers
    #     """
    #     network_list = []
    #     for each_server in server_ids_list:
    #         network = (self.server_client.list_addresses(each_server).entity)
    #         for each_network in network.private.addresses:
    #             if str(each_network.version) is '4':
    #                 network_list.append(
    #                     each_network.addr)
    #     return network_list

    # def _get_ports_from_otter_launch_configs(self, group_id):
    #     """
    #     Returns the list of ports in the luanch configs of the group_id
    #     """
    #     port_list = []
    #     launch_config = (
    #         self.autoscale_client.view_launch_config(group_id)).entity
    #     for each_lb in launch_config.loadBalancers:
    #         port_list.append(each_lb.port)
    #     return port_list


    # def _assert_lb_nodes_before_scale_persists_after_scale(self, lb_node_list_before_any_operation,
    #                                                        load_balancer_id):
    #     """
    #     Gets the current list of lb nodes address and asserts that provided node
    #     address list (which is before any scale operation) still exists within the
    #     current list of lb node addresses
    #     """
    #     current_lb_node_list = [each_node.address for each_node in
    #                             self._get_node_list_from_lb(load_balancer_id)]
    #     self.assertTrue(set(lb_node_list_before_any_operation).issubset(set(current_lb_node_list)),
    #                     msg='nodes {0} is not a subset of {1}'.format(set(
    #                         lb_node_list_before_any_operation),
    #                         set(current_lb_node_list)))

    # def _wait_for_servers_to_be_deleted_when_lb_invalid(self, group_id,
    #                                                     servers_before_lb, server_after_lb=0):
    #     """
    #     waits for servers_before_lb number of servers to be the desired capacity,
    #     then waits for the desired capacity to be server_after_lb when a group with an
    #     invalid load balancer is created.
    #     """
    #     end_time = time.time() + 600
    #     group_state = (self.autoscale_client.list_status_entities_sgroups(
    #         group_id)).entity
    #     if group_state.desiredCapacity is servers_before_lb:
    #         while time.time() < end_time:
    #             time.sleep(10)
    #             group_state = (self.autoscale_client.list_status_entities_sgroups(
    #                 group_id)).entity
    #             if group_state.desiredCapacity is server_after_lb:
    #                 return
    #         else:
    #             self.fail('Servers not deleted from group even when group has invalid'
    #                       ' load balancers!')
    #     else:
    #         self.fail('Number of servers building on the group are not as expected')
