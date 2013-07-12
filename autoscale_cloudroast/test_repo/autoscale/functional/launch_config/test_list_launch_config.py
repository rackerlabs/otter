"""
Test to launch config of a group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class ListLaunchConfigTest(AutoscaleFixture):

    """
    Verify launch config.
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group.
        """
        super(ListLaunchConfigTest, cls).setUpClass()
        cls.lc_disk_config = 'AUTO'
        cls.lc_personality = [{'path': '/root/.ssh/authorized_keys',
                               'contents': ('DQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp')}]
        cls.lc_metadata = {'lc_meta_key_1': 'lc_meta_value_1',
                           'lc_meta_key_2': 'lc_meta_value_2'}
        cls.lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'}]
        cls.lc_load_balancers = [{'loadBalancerId': 9099, 'port': 8080}]
        create_resp = cls.autoscale_behaviors.create_scaling_group_given(
            gc_name=cls.gc_name,
            gc_cooldown=cls.gc_cooldown,
            gc_min_entities=cls.gc_min_entities,
            lc_name=cls.lc_name,
            lc_image_ref=cls.lc_image_ref,
            lc_flavor_ref=cls.lc_flavor_ref,
            lc_personality=cls.lc_personality,
            lc_metadata=cls.lc_metadata,
            lc_disk_config=cls.lc_disk_config,
            lc_networks=cls.lc_networks,
            lc_load_balancers=cls.lc_load_balancers)
        cls.group = create_resp.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.launch_config_response = cls.autoscale_client.view_launch_config(
            cls.group.id)
        cls.launch_config = cls.launch_config_response.entity

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(ListLaunchConfigTest, cls).tearDownClass()

    def test_list_launch_config_response(self):
        """
        Verify the list config call for response code, headers and data.
        """
        self.assertEquals(self.launch_config_response.status_code, 200, msg='List launch'
                          'config failed with {0}' .format(self.launch_config_response.status_code))
        self.validate_headers(self.launch_config_response.headers)
        self.assertEquals(
            self.launch_config.server.name, self.autoscale_config.lc_name,
            msg='Prefix/Suffix server name in the launch config did not match')
        self.assertEquals(
            self.launch_config.server.flavorRef, self.autoscale_config.lc_flavor_ref,
            msg='Server flavor in the launch config did not match')
        self.assertEquals(
            self.launch_config.server.imageRef, self.autoscale_config.lc_image_ref,
            msg='Server ImageRef in the launch config did not match')
        self.assertEquals(self.autoscale_behaviors.personality_list(
                          self.launch_config.server.personality),
                          self.autoscale_behaviors.personality_list(
                              self.lc_personality),
                          msg='Server personality in the launch config did not match')
        self.assertEquals(
            self.autoscale_behaviors.to_data(
                self.launch_config.server.metadata),
            self.lc_metadata,
            msg='Server metadata in the launch config did not match')
        self.assertEquals(self.autoscale_behaviors.network_uuid_list(
                          self.launch_config.server.networks),
                          self.autoscale_behaviors.network_uuid_list(
                              self.lc_networks),
                          msg='Server networks did not match')
        self.assertEquals(
            self.autoscale_behaviors.lbaas_list(
                self.launch_config.loadBalancers),
            self.autoscale_behaviors.lbaas_list(
                self.lc_load_balancers),
            msg='Load balancers in the launch config did not match')
