"""
Test to negative cases for launch config.
"""
import unittest

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
        self.lc_name = rand_name('negative_launch_config')
        self.invalid_flavor_ids = ['INVALID-FLAVOR-ID', '8888', '-4', None]
        self.invalid_image_ids = ['INVALID-IMAGE-ID', '1111', self.lc_image_ref + 'Z', None]
        self.failing_id = ['']

    def test_update_scaling_group_launch_config_to_invalid_imageid(self):
        """
        Verify update launch config fails with a 400 when the new launch config
        has an invalid imageId.
        """
        group = self._create_group()
        for each_invalid_id in self.invalid_image_ids:
            update_launch_config_response = self.autoscale_client.update_launch_config(
                group_id=group.id,
                name=self.lc_name,
                image_ref=each_invalid_id,
                flavor_ref=self.lc_flavor_ref)
            self.assertEquals(update_launch_config_response.status_code, 400,
                              msg='Updating group with invalid server image id was successsful with'
                              ' response {0}'.format(update_launch_config_response.status_code))

    def test_update_scaling_group_launch_config_to_invalid_flavorid(self):
        """
        Verify update launch config fails with a 400 when the new launch config
        has an invalid flavorId.
        """
        group = self._create_group()
        for each_invalid_id in self.invalid_flavor_ids:
            update_launch_config_response = self.autoscale_client.update_launch_config(
                group_id=group.id,
                name=self.lc_name,
                image_ref=self.lc_image_ref,
                flavor_ref=each_invalid_id)
            self.assertEquals(update_launch_config_response.status_code, 400,
                              msg='Updating group with invalid flavor id was successsful with'
                              ' response {0}'.format(update_launch_config_response.status_code))

    def test_update_scaling_group_launch_config_to_invalid_flavorid_1(self):
        """
        Verify update launch config fails with a 400 when the new launch config
        has an flavorId of "1". This is special case where '1' flavor existed in Rackspace
        and has been taken out. But it still returns valid flavor when requested.
        """
        group = self._create_group()
        update_launch_config_response = self.autoscale_client.update_launch_config(
            group_id=group.id,
            name=self.lc_name,
            image_ref=self.lc_image_ref,
            flavor_ref='1')
        self.assertEquals(update_launch_config_response.status_code, 400,
                          msg='Updating group with invalid flavor id "1" was successsful with'
                          ' response {0}'.format(update_launch_config_response.status_code))

    def test_create_scaling_group_invalid_imageid(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has an invalid imageId.
        """
        for each_invalid_id in self.invalid_image_ids:
            create_group_response = self.autoscale_client.create_scaling_group(
                gc_name='test',
                gc_cooldown=self.gc_cooldown,
                gc_min_entities=self.gc_min_entities,
                lc_name=self.lc_name,
                lc_image_ref=each_invalid_id,
                lc_flavor_ref=self.lc_flavor_ref)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid server image id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))

    def test_create_scaling_group_invalid_flavorid(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has an invalid flavorid.
        """
        for each_invalid_id in self.invalid_flavor_ids:
            create_group_response = self.autoscale_client.create_scaling_group(
                gc_name='test',
                gc_cooldown=self.gc_cooldown,
                gc_min_entities=self.gc_min_entities,
                lc_name=self.lc_name,
                lc_image_ref=self.lc_image_ref,
                lc_flavor_ref=each_invalid_id)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid flavor id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))

    @unittest.skip('AUTO-875')
    def test_create_scaling_group_invalid_imageid_not_handled(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has imageId left blank. Note: Include failing_id as part of invalid_flavor_ids and
        invalid_image_ids, when this is fixed.
        """
        for each_invalid_id in self.failing_id:
            create_group_response = self.autoscale_client.create_scaling_group(
                gc_name='test',
                gc_cooldown=self.gc_cooldown,
                gc_min_entities=self.gc_min_entities,
                lc_name=self.lc_name,
                lc_image_ref=each_invalid_id,
                lc_flavor_ref=self.lc_flavor_ref)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid server image id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))

    @unittest.skip('AUTO-875')
    def test_create_scaling_group_invalid_flavorid_not_handled(self):
        """
        Verify scaling group creation fails with a 400 when launch config
        has flavorId left blank. Note: Include failing_id as part of invalid_flavor_ids and
        invalid_image_ids, when this is fixed.
        """
        for each_invalid_id in self.failing_id:
            create_group_response = self.autoscale_client.create_scaling_group(
                gc_name='test',
                gc_cooldown=self.gc_cooldown,
                gc_min_entities=self.gc_min_entities,
                lc_name=self.lc_name,
                lc_image_ref=self.lc_image_ref,
                lc_flavor_ref=each_invalid_id)
            self.assertEquals(create_group_response.status_code, 400,
                              msg='Create group with invalid flavor id was successsful with'
                              ' response {0}'.format(create_group_response.status_code))

    def _create_group(self):
        """
        Create a group
        """
        group_response = self.autoscale_behaviors.create_scaling_group_min()
        group = group_response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group
