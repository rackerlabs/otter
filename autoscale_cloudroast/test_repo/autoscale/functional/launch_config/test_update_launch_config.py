"""
Test to update launch config.
"""
from autoscale.models.request.autoscale_requests import null
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.tools.datagen import rand_name


class UpdateLaunchConfigTest(AutoscaleFixture):

    """
    Verify update launch config.
    """

    def setUp(self):
        """
        Create a scaling group.
        """
        super(UpdateLaunchConfigTest, self).setUp()
        group_response = self.autoscale_behaviors.create_scaling_group_min()
        self.group = group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)

    def test_update_launch_config_response(self):
        """
        Verify the update launch config call for response code, headers and data.
        """
        lc_name = rand_name('upd_server_name')
        lc_image_ref = self.lc_image_ref_alt
        lc_flavor_ref = '4'
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
                          msg='Update launch config failed with {0} as against a 204 for group'
                          ' {1}'.format(update_lc_response.status_code, self.group.id))
        self.validate_headers(update_lc_response.headers)
        self.assertEquals(updated_launchconfig.server.name, lc_name,
                          msg='Prefix/Suffix server name in the launch config did not update '
                          'for group {0}'.format(self.group.id))
        self.assertEquals(
            updated_launchconfig.server.flavorRef, lc_flavor_ref,
            msg='Server flavor in the launch config did not update '
            'for group {0}'.format(self.group.id))
        self.assertEquals(
            updated_launchconfig.server.imageRef, lc_image_ref,
            msg='Server ImageRef in the launch config did not update '
            'for group {0}'.format(self.group.id))
        self.assertEquals(
            self.autoscale_behaviors.personality_list(
                updated_launchconfig.server.personality),
            self.autoscale_behaviors.personality_list(
                lc_personality),
            msg='Server personality in the launch config did not update '
            'for group {0}'.format(self.group.id))
        self.assertEquals(
            self.autoscale_behaviors.to_data(
                updated_launchconfig.server.metadata),
            lc_metadata,
            msg='Server metadata in the launch config did not update '
            'for group {0}'.format(self.group.id))
        self.assertEquals(
            self.autoscale_behaviors.network_uuid_list(
                updated_launchconfig.server.networks),
            self.autoscale_behaviors.network_uuid_list(
                lc_networks),
            msg='Server networks did not update '
            'for group {0}'.format(self.group.id))
        self.assertEquals(
            self.autoscale_behaviors.lbaas_list(
                updated_launchconfig.loadBalancers),
            self.autoscale_behaviors.lbaas_list(
                lc_load_balancers),
            msg='Load balancers in the launch config did not update '
            'for group {0}'.format(self.group.id))

    def test_partial_update_launch_config(self):
        """
        Update launch config with partial request does not fail with 403, and overwrites the
        the launch config as per the latest request
        """
        lc_name = rand_name('upd_server_name')
        lc_image_ref = self.lc_image_ref_alt
        lc_flavor_ref = '4'
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
                          msg='Update launch config failed with {0} as against a 204, success for'
                          ' group {1}'.format(update_lc_response.status_code, self.group.id))
        lc_name = 'test_upd_lc'
        image_ref = self.lc_image_ref
        flavor_ref = '8'
        update_launchconfig_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=lc_name,
            image_ref=image_ref,
            flavor_ref=flavor_ref)
        self.assertEquals(update_launchconfig_response.status_code, 204,
                          msg='Update launch config does not allow partial requests'
                          ' for group {0}'.format(self.group.id))

    def _test_boot_from_volume(self, lc_image_ref):
        """
        Helper to assert that updating boot from volume works
        """
        lc_name = rand_name('boot_from_volume')
        lc_flavor_ref = self.lc_flavor_ref
        update_lc_response = self.autoscale_client.update_launch_config(
            group_id=self.group.id,
            name=lc_name,
            image_ref=lc_image_ref,
            flavor_ref=lc_flavor_ref)

        self.assertEquals(update_lc_response.status_code, 204,
                          msg='Update launch config failed with {0} as against a 204, success for'
                          ' group {1}'.format(update_lc_response.status_code, self.group.id))
        self.validate_headers(update_lc_response.headers)

        launchconfig_response = self.autoscale_client.view_launch_config(
            self.group.id)
        updated_launchconfig = launchconfig_response.entity

        # None is no argument, null is null.  Yes this is terrible.
        # Cloudcafe removes arguments from the json if the value is None.
        # So a null value was hacked in to be 'null'
        if lc_image_ref is None:
            self.assertFalse(hasattr(updated_launchconfig.server, 'imageRef'))
        elif lc_image_ref is null:
            self.assertEquals(
                updated_launchconfig.server.imageRef, None,
                msg='Server ImageRef in the launch config did not update '
                'for group {0}'.format(self.group.id))
        else:
            self.assertEquals(
                updated_launchconfig.server.imageRef, lc_image_ref,
                msg='Server ImageRef in the launch config did not update '
                'for group {0}'.format(self.group.id))

    def test_update_launch_config_with_boot_from_volume_empty_image(self):
        """
        Update a scaling group's launch config with an empty image ID.  Request
        succeeds, overwriting previous launch config.

        TODO: once block_device_mapping is validated (because image ID should
        only be empty if ``block_device_mapping`` is specified), the
        ``update_launch_config`` function should take ``block_device_mapping``
        (the autoscale and nova fixtures should be updated), and the
        updated launch config in autoscale should be checked for
        ``block_device_mapping``.
        """
        self._test_boot_from_volume("")

    def test_update_launch_config_with_boot_from_volume_null_image(self):
        """
        Update a scaling group's launch config with a null image ID.  Request
        succeeds, overwriting previous launch config.

        TODO: once block_device_mapping is validated (because image ID should
        only be empty if ``block_device_mapping`` is specified), the
        ``update_launch_config`` function should take ``block_device_mapping``
        (the autoscale and nova fixtures should be updated), and the
        updated launch config in autoscale should be checked for
        ``block_device_mapping``.
        """
        self._test_boot_from_volume(null)

    def test_update_launch_config_with_boot_from_volume_no_image(self):
        """
        Update a scaling group's launch config without an image ID.  Request
        succeeds, overwriting previous launch config.

        TODO: once block_device_mapping is validated (because image ID should
        only be empty if ``block_device_mapping`` is specified), the
        ``update_launch_config`` function should take ``block_device_mapping``
        (the autoscale and nova fixtures should be updated), and the
        updated launch config in autoscale should be checked for
        ``block_device_mapping``.
        """
        self._test_boot_from_volume(None)
