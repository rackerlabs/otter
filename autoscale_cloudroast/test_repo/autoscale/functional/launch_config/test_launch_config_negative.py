"""
Test to negative cases for launch config.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.tools.datagen import rand_name


class LaunchConfigNegtaiveTest(AutoscaleFixture):

    """
    Verify launch config.
    """

    def setUp(self):
        """
        Create a scaling group.
        """
        super(LaunchConfigNegtaiveTest, self).setUp()
        group_response = self.autoscale_behaviors.create_scaling_group_min()
        self.group = group_response.entity
        self.resources.add(self.group.id,
                           self.autoscale_client.delete_scaling_group)
        self.lc_name = rand_name('negative_launch_config')
        self.invalid_flavor_ids = ['INVALID-FLAVOR-ID', 8888, 1, -4]
        self.invalid_image_ids = ['INVALID-IMAGE-ID', 1111, self.lc_image_ref + 'Z']

    def test_update_scaling_group_launch_config_to_invalid_imageid(self):
        """
        Verify update luanch config fails with a 400 when the new launch config
        has an invalid imageId.
        """
        for each_invalid_id in self.invalid_image_ids:
            update_launch_config_response = self.autoscale_client.update_launch_config(
                group_id=self.group.id,
                name=self.lc_name,
                image_ref=each_invalid_id,
                flavor_ref=self.lc_flavor_ref)
            self.assertEquals(update_launch_config_response.status_code, 400,
                              msg='Updating group with invalid server image id was successsful with'
                              ' response {0}'.format(update_launch_config_response.status_code))

    def test_update_scaling_group_launch_config_to_invalid_flavorid(self):
        """
        Verify update luanch config fails with a 400 when the new launch config
        has an invalid flavorId.
        """
        for each_invalid_id in self.invalid_flavor_ids:
            update_launch_config_response = self.autoscale_client.update_launch_config(
                group_id=self.group.id,
                name=self.lc_name,
                image_ref=self.lc_image_ref,
                flavor_ref=each_invalid_id)
            self.assertEquals(update_launch_config_response.status_code, 400,
                              msg='Updating group with invalid server image id was successsful with'
                              ' response {0}'.format(update_launch_config_response.status_code))

    def test_create_scaling_group_invalid_imageid(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has an invalid imageId.
        """
        for each_invalid_id in self.invalid_image_ids:
            create_group_response = self.autoscale_behaviors.create_scaling_group_given(
                gc_min_entities=self.gc_min_entities,
                lc_image_ref=each_invalid_id)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid server image id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))

    def test_create_scaling_group_invalid_flavorid(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has an invalid flavorid.
        """
        for each_invalid_id in self.invalid_flavor_ids:
            create_group_response = self.autoscale_behaviors.create_scaling_group_given(
                gc_min_entities=self.gc_min_entities,
                lc_flavor_ref=each_invalid_id)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid server image id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))
