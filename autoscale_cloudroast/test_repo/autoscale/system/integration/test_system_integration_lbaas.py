"""
System Integration tests autoscaling with lbaas
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import random


class AutoscaleLbaasFixture(AutoscaleFixture):

    """
    System tests to verify lbaas integration with autoscale
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(AutoscaleLbaasFixture, cls).setUpClass()
        # create 3 lbaas in the given region and one in a different region
        cls.lbaas1_id = '142427'
        cls.lbaas2_id = '155337'
        cls.lbaas3_id = '155465'
        cls.lbaas_other_region = '155467'

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(AutoscaleLbaasFixture, cls).tearDownClass()
        # delete all lbaas

    def test_add_multiple_lbaas_to_group(self):
        """
        Adding multiple lbaas within the launch config when creating the group,
        cause the servers to be added as nodes to all the lbaas
        """
        group = self._create_group_given_lbaas_id(self, self.lbaas1_id,
                                                  self.lbaas2_id, self.lbaas3_id)
        active_server_list = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._verify_lbs_on_group_have_servers_as_nodes(active_server_list,
                                                        self.lbaas1_id, self.lbaas2_id,
                                                        self.lbaas3_id)

    def test_update_launch_config_to_include_multiple_lbaas(self):
        """
        Updating the launch config to add multiple lbaas to a group that had only one lbaas,
        results in the new servers of that group to be added as nodes to all the lbaas'
        """
        pass

    def test_update_launch_config_to_include_lbaas(self):
        """
        Update the launch config to add a lbaas to a group that did not have an lbaas,
        results in the new servers of that group to be added as nodes to the lbaas
        """
        pass

    def test_update_existing_lbaas_in_launch_config(self):
        """
        Update the lbaas id in the launch config and verify a scale up after the update,
        resulted in servers added as nodes to the newly added lbaas
        """
        pass

    def test_remove_existing_lbaas_in_launch_config(self):
        """
        Remove lbaas id in the launch config and verify a scale up after the update,
        resulted in servers not added to the older lbaas id
        """
        pass

    def test_add_nodes_to_existing_lbaas(self):
        """
        Add an existing lbaas to a scaling group with minentities > 0. The servers
        on the scaling group are added as nodes to the loadbalancer
        """
        pass

    def test_negative_add_nodes_to_different_accounts_lbaas(self):
        """
        Create an lbaas on diffrent account and add it in the launch config and
        verify scaling group
        """
        pass

    def test_negative_add_nodes_to_deleted_lbaas(self):
        """
        Delete an lbaas that is added to a scaling group's launch config
        and execute policy and verify
        """
        pass

    def test_negative_create_group_with_lbaas_in_different_region(self):
        """
        Create a group with minentities > 0 and lbaas on different region.
        No active servers remain on the group.
        """
        pass

    def test_update_server_and_lbaas_config_scale_up_down(self):
        """
        Create a group and then update group launch config for server and lbaas,
        verify all updates reflect on servers created from the scale up after the update
        """
        pass

    def test_update_server_and_lbaas_config_scale_up_down_scheduler(self):
        """
        Create a group and then update group launch config for server and lbaas,
        verify all updates reflect on servers created from the scale up after the update
        """
        pass

    def _create_group_given_lbaas_id(self, *lbaas_ids):
        """
        Given the args, creates a group with minentities > 0 and the given number of lbaas
        Note: The lbaas are excepted to be present on the account
        """
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt,
            lc_load_balancers=self._create_lbaas_list(*lbaas_ids))
        group = create_group_response
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        return group

    def _verify_lbs_on_group_have_servers_as_nodes(self, server_ids_list, *lbaas_id):
        """
        Given the list of active server ids on the group, create a list of the
        ip address of the servers on the group,
        and compare it to the list of ip addresses got from a list node
        call for the lbaas id.
        Get list of port of lbaas on the group and compare to the list of
        port on the lbaas id.
        """
        # call nova list server, filter by ID and create ip address list
        # call list node for each lbaas, create list of Ips and ports
        # call otter, list launch config, create list of ports
        # compare ip address lists and port lists
        pass

    def _update_launch_config(self, group, *lbaas_ids):
        """
        Update the launch config to update to the given lbaas id
        """
        update_lc_response = self.autoscale_client.update_launch_config(
            name=group.launchConfiguration.server.name,
            image_ref=group.launchConfiguration.server.imageRef,
            flavor_ref=group.launchConfiguration.server.flavorRef,
            personality=None,
            metadata=None,
            disk_config=None,
            networks=None,
            load_balancers=self._create_lbaas_list(*lbaas_ids))
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
