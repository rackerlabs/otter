"""
Test to update launch config.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture
from cloudcafe.common.tools.datagen import rand_name


class UpdateLaunchConfigTest(ScalingGroupFixture):

    """
    Verify update launch config.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(UpdateLaunchConfigTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(UpdateLaunchConfigTest, cls).tearDownClass()

    def test_update_launch_config_response(self):
        """
        Verify the update launch config call for response code, headers and data.
        """
        lc_name = rand_name('upd_server_name')
        lc_image_ref = 'XYZ'
        lc_flavor_ref = 4
        lc_load_balancers = [{'loadBalancerId': 1234, 'port': 8181}]
        lc_disk_config = 'AUTO'
        lc_personality = [{'path': '/root/.ssh/authorized_keys',
                           'contents': ('DQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp')}]
        lc_metadata = {'lc_meta_key_1': 'lc_meta_value_1',
                       'lc_meta_key_2': 'lc_meta_value_2'}
        lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'}]
        update_lc_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=lc_name,
            image_ref=lc_image_ref,
            flavor_ref=lc_flavor_ref,
            personality=lc_personality,
            metadata=lc_metadata,
            disk_config=lc_disk_config,
            networks=lc_networks,
            load_balancers=lc_load_balancers)
        launchconfig_response = self.autoscale_client.view_launch_config(
            self.group.id)
        updated_launchconfig = launchconfig_response.entity
        self.assertEquals(update_lc_response.status_code, 204,
                          msg='Update launch config failed with {0} as against a 204'
                          .format(update_lc_response.status_code))
        self.validate_headers(update_lc_response.headers)
        self.assertEquals(updated_launchconfig.server.name, lc_name,
                          msg='Prefix/Suffix server name in the launch config did not update')
        self.assertEquals(
            updated_launchconfig.server.flavorRef, lc_flavor_ref,
            msg='Server flavor in the launch config did not update')
        self.assertEquals(
            updated_launchconfig.server.imageRef, lc_image_ref,
            msg='Server ImageRef in the launch config did not update')
        self.assertEquals(
            self.autoscale_behaviors.personality_list(
                updated_launchconfig.server.personality),
            self.autoscale_behaviors.personality_list(
                lc_personality),
            msg='Server personality in the launch config did not update')
        self.assertEquals(
            self.autoscale_behaviors.to_data(
                updated_launchconfig.server.metadata),
            lc_metadata,
            msg='Server metadata in the launch config did not update')
        self.assertEquals(
            self.autoscale_behaviors.network_uuid_list(
                updated_launchconfig.server.networks),
            self.autoscale_behaviors.network_uuid_list(
                lc_networks),
            msg='Server networks did not update')
        self.assertEquals(
            self.autoscale_behaviors.lbaas_list(
                updated_launchconfig.loadBalancers),
            self.autoscale_behaviors.lbaas_list(
                lc_load_balancers),
            msg='Load balancers in the launch config did not update')

    def test_partial_update_launch_config(self):
        """
        Update launch config with partial request does not fail with 403, and overwrites the
        the launch config as per the latest request
        """
        lc_name = rand_name('upd_server_name')
        lc_image_ref = 'XYZ'
        lc_flavor_ref = 4
        lc_load_balancers = [{'loadBalancerId': 1234, 'port': 8181}]
        lc_disk_config = 'AUTO'
        lc_personality = [{'path': '/root/.ssh/authorized_keys',
                           'contents': ('DQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp')}]
        lc_metadata = {'lc_meta_key_1': 'lc_meta_value_1',
                       'lc_meta_key_2': 'lc_meta_value_2'}
        lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'}]
        update_lc_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=lc_name,
            image_ref=lc_image_ref,
            flavor_ref=lc_flavor_ref,
            personality=lc_personality,
            metadata=lc_metadata,
            disk_config=lc_disk_config,
            networks=lc_networks,
            load_balancers=lc_load_balancers)
        self.assertEquals(update_lc_response.status_code, 204,
                          msg='Update launch config failed with {0} as against a 204, success'
                          .format(update_lc_response.status_code))
        lc_name = "test_upd_lc"
        image_ref = "88876868"
        flavor_ref = "0"
        update_launchconfig_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=lc_name,
            image_ref=image_ref,
            flavor_ref=flavor_ref)
        self.assertEquals(update_launchconfig_response.status_code, 204,
                          msg="Update launch config does not allow partial requests")
