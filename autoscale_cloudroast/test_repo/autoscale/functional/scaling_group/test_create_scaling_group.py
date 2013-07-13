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

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group with all the fields.
        """
        super(CreateScalingGroupTest, cls).setUpClass()
        cls.gc_name = rand_name('testscalinggroup')
        cls.gc_max_entities = 10
        cls.gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                           'gc_meta_key_2': 'gc_meta_value_2'}
        cls.file_contents = 'This is a test file.'
        cls.lc_personality = [{'path': '/root/.csivh',
                               'contents': base64.b64encode(cls.file_contents)}]
        cls.lc_metadata = {'meta_key_1': 'meta_value_1',
                           'meta_key_2': 'meta_value_2'}
        cls.lc_disk_config = 'AUTO'
        cls.lc_networks = [{'uuid': '11111111-1111-1111-1111-111111111111'},
                           {'uuid': '00000000-0000-0000-0000-000000000000'}]
        cls.lc_load_balancers = [{'loadBalancerId': 9099, 'port': 8080}]
        cls.sp_list = [{
            'name': 'scale up by 1',
            'change': 1,
            'cooldown': 0,
            'type': 'webhook'
        }]
        cls.create_resp = cls.autoscale_client.create_scaling_group(
            gc_name=cls.gc_name,
            gc_cooldown=cls.gc_cooldown,
            gc_min_entities=cls.gc_min_entities,
            gc_max_entities=cls.gc_max_entities,
            gc_metadata=cls.gc_metadata,
            lc_name=cls.lc_name,
            lc_image_ref=cls.lc_image_ref,
            lc_flavor_ref=cls.lc_flavor_ref,
            lc_personality=cls.lc_personality,
            lc_metadata=cls.lc_metadata,
            lc_disk_config=cls.lc_disk_config,
            lc_networks=cls.lc_networks,
            lc_load_balancers=cls.lc_load_balancers,
            sp_list=cls.sp_list)
        cls.scaling_group = cls.create_resp.entity
        cls.resources.add(cls.scaling_group.id,
                          cls.autoscale_client.delete_scaling_group)

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(CreateScalingGroupTest, cls).tearDownClass()

    def test_create_scaling_group_response(self):
        """
        Verify the response code for the create scaling group is 201
        """
        self.assertTrue(self.create_resp.ok,
                        msg='Create scaling group call failed with API Response: {0}'
                        .format(self.create_resp.content))
        self.assertEquals(self.create_resp.status_code, 201,
                          msg='The create failed with {0}'
                          .format(self.create_resp.status_code))
        self.validate_headers(self.create_resp.headers)

    def test_create_scaling_group_fields(self):
        """
        Verify the scaling group id and links exist in the response
        """
        self.assertTrue(self.scaling_group.id is not None,
                        msg='Scaling Group id was not set in the response')
        self.assertTrue(self.scaling_group.links is not None,
                        msg='Scaling Group links were not set in the response')

    def test_created_scaling_group_groupconfig_fields(self):
        """
        Verify the group configuration of the group is as expected.
        """
        self.assertEqual(
            self.gc_name, self.scaling_group.groupConfiguration.name,
            msg='Scaling group name did not match')
        self.assertEqual(self.gc_min_entities,
                         self.scaling_group.groupConfiguration.minEntities,
                         msg='Scaling group minEntities did not match')
        self.assertEqual(self.gc_max_entities,
                         self.scaling_group.groupConfiguration.maxEntities,
                         msg='Scaling group maxEntities did not match')
        self.assertEqual(self.gc_cooldown,
                         self.scaling_group.groupConfiguration.cooldown,
                         msg='Scaling group cooldown did not match')
        self.assertEqual(self.gc_metadata,
                         self.autoscale_behaviors.to_data(
                             self.scaling_group.groupConfiguration.metadata),
                         msg='Scaling group metadata did not match')

    def test_created_scaling_group_launchconfig_scalingpolicy_fields(self):
        """
        Verify the launch configuration on the group is as expected.
        """
        self.assertEqual(self.autoscale_config.lc_name,
                         self.scaling_group.launchConfiguration.server.name,
                         msg='Server name provided in the launch config did not match')
        self.assertEqual(self.autoscale_config.lc_image_ref,
                         self.scaling_group.launchConfiguration.server.imageRef,
                         msg='Image id did not match')
        self.assertEqual(self.autoscale_config.lc_flavor_ref,
                         self.scaling_group.launchConfiguration.server.flavorRef,
                         msg='Flavor id did not match')
        self.assertEquals(
            self.autoscale_behaviors.network_uuid_list(self.lc_networks),
            self.autoscale_behaviors.network_uuid_list(
                self.scaling_group.launchConfiguration.server.networks),
            msg='Networks within the launch config did not match')
        self.assertEquals(
            self.autoscale_behaviors.personality_list(self.lc_personality),
            self.autoscale_behaviors.personality_list(
                self.scaling_group.launchConfiguration.server.personality),
            msg='Personality within the launch config did not match')
        self.assertEqual(
            self.autoscale_behaviors.lbaas_list(self.lc_load_balancers),
            self.autoscale_behaviors.lbaas_list(
                self.scaling_group.launchConfiguration.loadBalancers),
            msg='Load balancers did not match')
        self.assertEqual(
            self.autoscale_behaviors.policy_details_list(self.sp_list),
            self.autoscale_behaviors.policy_details_list(
                self.scaling_group.scalingPolicies),
            msg='Scaling policies of the scaling group did not match')
