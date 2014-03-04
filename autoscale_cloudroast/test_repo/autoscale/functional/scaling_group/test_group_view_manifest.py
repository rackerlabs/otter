"""
Test to create and verify group manifest.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class GroupViewManifestTest(AutoscaleFixture):

    """
    Verify the view manifest for a group.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(GroupViewManifestTest, cls).setUpClass()
        create_group = cls.autoscale_behaviors.create_scaling_group_min()
        cls.group = create_group.entity
        cls.resources.add(
            cls.group.id, cls.autoscale_client.delete_scaling_group)

    def test_get_scaling_group(self):
        """
        Verify the get group for response code 200, headers and data.
        """
        group_info_response = self.autoscale_client.view_manifest_config_for_scaling_group(
            group_id=self.group.id)
        group_info = group_info_response.entity
        self.assertEqual(200, group_info_response.status_code,
                         msg='The get scaling group call failed with {0} for group'
                         ' {1}'.format(group_info_response.status_code,
                                       self.group.id))
        self.validate_headers(group_info_response.headers)
        self.assertEqual(group_info.id, self.group.id,
                         msg='Group id did not match for group '
                         '{0}'.format(self.group.id))
        self.assertEqual(group_info.groupConfiguration.name,
                         self.group.groupConfiguration.name,
                         msg='Group name did not match for group '
                         '{0}'.format(self.group.id))
        self.assertEqual(group_info.groupConfiguration.minEntities,
                         self.group.groupConfiguration.minEntities,
                         msg="Group's minimum entities did not match for group "
                         "{0}".format(self.group.id))
        self.assertEqual(group_info.launchConfiguration,
                         self.group.launchConfiguration,
                         msg="Group's launch configurations did not match for group "
                         '{0}'.format(self.group.id))
        self.assert_group_state(group_info.state)
