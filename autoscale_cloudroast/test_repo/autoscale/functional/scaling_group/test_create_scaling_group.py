"""
Test to create and verify the created group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import base64
from cloudcafe.common.tools.datagen import rand_name


class CreateScalingGroupTest(AutoscaleFixture):

    """
    Verify create group.
    """

    def _create_scaling_group(self):
        """
        Create a scaling group with all the fields.
        """
        self.gc_name = rand_name('testscalinggroup')
        self.gc_max_entities = 10
        self.gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                            'gc_meta_key_2': 'gc_meta_value_2'}
        self.file_contents = 'This is a test file.'
        self.lc_personality = [{'path': '/root/.csivh',
                                'contents': base64.b64encode(self.file_contents)}]
        self.lc_metadata = {'meta_key_1': 'meta_value_1',
                            'meta_key_2': 'meta_value_2'}
        self.lc_disk_config = 'AUTO'
        self.lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'},
                            {'uuid': '00000000-0000-0000-0000-000000000000'}]
        self.lc_load_balancers = [{'loadBalancerId': 9099, 'port': 8080}]
        self.sp_list = [{
            'name': 'scale up by 1',
            'change': 1,
            'cooldown': 0,
            'type': 'webhook'
        }]

        self.create_resp = self.autoscale_client.create_scaling_group(
            gc_name=self.gc_name,
            gc_cooldown=self.gc_cooldown,
            gc_min_entities=self.gc_min_entities,
            gc_max_entities=self.gc_max_entities,
            gc_metadata=self.gc_metadata,
            lc_name=self.lc_name,
            lc_image_ref=self.lc_image_ref,
            lc_flavor_ref=self.lc_flavor_ref,
            lc_personality=self.lc_personality,
            lc_metadata=self.lc_metadata,
            lc_disk_config=self.lc_disk_config,
            lc_networks=self.lc_networks,
            lc_load_balancers=self.lc_load_balancers,
            sp_list=self.sp_list,
            network_type='public')
        self.scaling_group = self.create_resp.entity
        self.resources.add(self.scaling_group.id,
                           self.autoscale_client.delete_scaling_group)

    def _test_create_scaling_group_response(self):
        """
        Verify the response code for the create scaling group is 201
        """
        self.assertTrue(self.create_resp.ok,
                        msg='Create scaling group call failed with API Response: {0} for '
                        'group {1}'.format(self.create_resp.content, self.scaling_group.id))
        self.assertEquals(self.create_resp.status_code, 201,
                          msg='The create failed with {0} for group '
                          '{1}'.format(self.create_resp.status_code, self.scaling_group.id))
        self.validate_headers(self.create_resp.headers)

    def _test_create_scaling_group_fields(self):
        """
        Verify the scaling group id and links exist in the response
        """
        self.assertTrue(self.scaling_group.id is not None,
                        msg='Scaling Group id was not set in the response'
                        ' for group {0}'.format(self.scaling_group.id))
        self.assertTrue(self.scaling_group.links is not None,
                        msg='Scaling Group links were not set in the response'
                        ' for group {0}'.format(self.scaling_group.id))

    def _test_created_scaling_group_groupconfig_fields(self):
        """
        Verify the group configuration of the group is as expected.
        """
        self.assertEqual(
            self.gc_name, self.scaling_group.groupConfiguration.name,
            msg='Scaling group name did not match'
            ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.gc_min_entities,
                         self.scaling_group.groupConfiguration.minEntities,
                         msg='Scaling group minEntities did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.gc_max_entities,
                         self.scaling_group.groupConfiguration.maxEntities,
                         msg='Scaling group maxEntities did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.gc_cooldown,
                         self.scaling_group.groupConfiguration.cooldown,
                         msg='Scaling group cooldown did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.gc_metadata,
                         self.autoscale_behaviors.to_data(
                             self.scaling_group.groupConfiguration.metadata),
                         msg='Scaling group metadata did not match'
                         ' for group {0}'.format(self.scaling_group.id))

    def _test_created_scaling_group_launchconfig_scalingpolicy_fields(self):
        """
        Verify the launch configuration on the group is as expected.
        """
        self.assertEqual(self.lc_name,
                         self.scaling_group.launchConfiguration.server.name,
                         msg='Server name provided in the launch config did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.lc_image_ref,
                         self.scaling_group.launchConfiguration.server.imageRef,
                         msg='Image id did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(self.lc_flavor_ref,
                         self.scaling_group.launchConfiguration.server.flavorRef,
                         msg='Flavor id did not match'
                         ' for group {0}'.format(self.scaling_group.id))
        self.assertEquals(
            self.autoscale_behaviors.network_uuid_list(self.lc_networks),
            self.autoscale_behaviors.network_uuid_list(
                self.scaling_group.launchConfiguration.server.networks),
            msg='Networks within the launch config did not match'
            ' for group {0}'.format(self.scaling_group.id))
        self.assertEquals(
            self.autoscale_behaviors.personality_list(self.lc_personality),
            self.autoscale_behaviors.personality_list(
                self.scaling_group.launchConfiguration.server.personality),
            msg='Personality within the launch config did not match'
            ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(
            self.autoscale_behaviors.lbaas_list(self.lc_load_balancers),
            self.autoscale_behaviors.lbaas_list(
                self.scaling_group.launchConfiguration.loadBalancers),
            msg='Load balancers did not match'
            ' for group {0}'.format(self.scaling_group.id))
        self.assertEqual(
            self.autoscale_behaviors.policy_details_list(self.sp_list),
            self.autoscale_behaviors.policy_details_list(
                self.scaling_group.scalingPolicies),
            msg='Scaling policies of the scaling group did not match'
            ' for group {0}'.format(self.scaling_group.id))

    def _test_created_scaling_group_state_fields(self):
        """
        Verify the state on the group is as expected.
        """
        self.assert_group_state(self.scaling_group.state)

    def test_create_scaling_group_success_response(self):
        """
        Create a scaling group, and test all aspects of the response as defined
        in the _test_* cases above.
        """
        self._create_scaling_group()
        self._test_create_scaling_group_response()
        self._test_create_scaling_group_fields()
        self._test_created_scaling_group_groupconfig_fields()
        self._test_created_scaling_group_launchconfig_scalingpolicy_fields()

    def test_create_scaling_group_with_boot_from_volume_empty_image(self):
        """
        Create a scaling group with an empty image ID, and test that the
        response is successful and that all the launch config fields match
        what was created.

        TODO: once block_device_mapping is validated (because image ID should
        only be empty if ``block_device_mapping`` is specified), the create
        scaling group function should take ``block_device_mapping`` (the
        autoscale and nova fixtures should be updated), and
        :func:`_test_created_scaling_group_launchconfig_scalingpolicy_fields`
        should test whether ``block_device_mapping`` matches.
        """
        self.lc_image_ref = ""
        self._create_scaling_group()
        self._test_create_scaling_group_response()
        self._test_created_scaling_group_launchconfig_scalingpolicy_fields()

    def test_create_scaling_group_with_boot_from_volume_null_image(self):
        """
        Create a scaling group with a None image ID, and test that the
        response is successful and that all the launch config fields match
        what was created.

        TODO: once block_device_mapping is validated (because image ID should
        only be empty if ``block_device_mapping`` is specified), the create
        scaling group function should take ``block_device_mapping`` (the
        autoscale and nova fixtures should be updated), and
        :func:`_test_created_scaling_group_launchconfig_scalingpolicy_fields`
        should test whether ``block_device_mapping`` matches.
        """
        self.lc_image_ref = None
        self._create_scaling_group()
        self._test_create_scaling_group_response()
        self._test_created_scaling_group_launchconfig_scalingpolicy_fields()
