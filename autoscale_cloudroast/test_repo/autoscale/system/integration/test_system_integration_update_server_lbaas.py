"""
System Integration tests autoscaling with updates to nova and lbaas
in the launch config of the group
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import base64


class AutoscaleLbaasFixture(AutoscaleFixture):

    """
    System tests to verify nova and lbaas integration with autoscale
    """
    @classmethod
    def setUpClass(cls):
        cls.image_ref = cls.lc_image_ref_alt
        cls.flavor_ref = 3
        file_contents = 'This is a test file.'
        cls.personality = [{'path': '/root/.csivh',
                            'contents': base64.b64encode(file_contents)}]
        cls.metadata = {'gc_meta_key_1': 'gc_meta_value_1'}
        cls.disk_config = 'AUTO'
        cls.lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'},
                           {'uuid': '00000000-0000-0000-0000-000000000000'}]
        cls.load_balancers = [{
            'loadBalancerId': cls.load_balancer_1, 'port': 8080}]
        cls.policy_up_data = {'change': cls.sp_change}
        cls.policy_down_data = {'change': cls.sp_change}

    def test_update_server_and_lbaas_config_scale_up_down(self):
        """
        Create a group and then update group launch config for server and lbaas,
        verify all updates reflect on servers created from the scale up after the update
        """
        group = (self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt)).entity
        active_servers = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt)
        self._update_launch_config(group.id)
        self.autoscale_behaviors.create_policy_webhook(
            group.id, self.policy_up_data, execute_policy=True)
        activeservers_after_scale = self.autoscale_behaviors.wait_for_expected_number_of_active_servers(
            group.id,
            self.gc_min_entities_alt + self.sp_change)
        servers_after_scale_up = set(
            activeservers_after_scale) - set(active_servers)


    # def test_update_server_and_lbaas_config_scale_up_down_scheduler(self):
    #     """
    #     Create a group and then update group launch config for server and lbaas,
    #     verify all updates reflect on servers created from the scale up after the update
    #     """
    #     pass
    def _update_launch_config(self, group_id):
        """
        Update the launch config to update to the given load balancer ids
        """
        update_lc_response = self.autoscale_client.update_launch_config(
            group_id=group_id,
            name='updated_lc',
            image_ref=self.image_ref,
            flavor_ref=self.flavor_ref,
            personality=self.personality,
            metadata=self.metadata,
            disk_config=self.disk_config,
            networks=self.networks,
            load_balancers=self.load_balancers)
        self.assertEquals(update_lc_response.status_code, 204,
                          msg='Update launch config with load balancer failed for group '
                          '{0} with {1}'.format(group_id, update_lc_response.status_code))

    def _verify_server_list_for_launch_config(self, server_list):
        for each in list(server_list):
            get_server_resp = self.server_client.get_server(each)
            server = get_server_resp.entity
            self.assertTrue('updated_lc' in server.name)
            self.assertEquals(server.image.id, self.image_ref)
            self.assertEquals(server.flavor.id, self.flavor_ref)
            self.assertEquals(
                self.autoscale_behaviors.network_uuid_list(self.lc_networks),
                self.autoscale_behaviors.network_uuid_list(server.networks))
        self.assertEquals(
            self.autoscale_behaviors.personality_list(self.lc_personality),
            self.autoscale_behaviors.personality_list(server.personality))
        self.assertEquals(self.metadata,
                          self.autoscale_behaviors.to_data(server.metadata))
