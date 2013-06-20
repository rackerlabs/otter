"""
Test to create and verify delete group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteScalingGroupTest(AutoscaleFixture):
    """
    Verify delete group.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(DeleteScalingGroupTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(DeleteScalingGroupTest, cls).tearDownClass()

    def test_delete_group_with_mimEntities_over_0(self):
        """
        Verify delete group when group has over 0 min entities.
        """
        # AUTO-284 with invalid tenant
        create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=self.gc_min_entities_alt)
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {}'
                              .format(create_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 403,
                          msg='The delete should have failed but passed with {}'
                              .format(delete_resp.status_code))

    def test_delete_group_with_0_minentities(self):
        """
        Verify delete group when group has 0 min entities.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {}'
                              .format(create_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete failed with {}'
                              .format(delete_resp.status_code))

    def test_delete_invalid_groupid(self):
        """
        Verify delete group with invalid group id.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {}'
                              .format(create_resp.status_code))
        group.id += 'xyz'
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete failed with {}'
                              .format(delete_resp.status_code))

    def test_delete_already_deleted_group(self):
        """
        Verify delete group with an already deleted group.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {}'
                              .format(create_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete failed with {}'
                              .format(delete_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete failed with {}'
                              .format(delete_resp.status_code))
