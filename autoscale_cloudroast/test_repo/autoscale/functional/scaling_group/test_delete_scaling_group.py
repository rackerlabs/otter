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

    def test_delete_group_with_0_minentities(self):
        """
        Verify delete group returns response code 204 when group has 0 min entities.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {0}'
                              .format(create_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete failed with {0}'
                              .format(delete_resp.status_code))

    def test_delete_invalid_groupid(self):
        """
        Verify delete group with invalid group id returns 404.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {0}'
                              .format(create_resp.status_code))
        group.id += 'xyz'
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete failed with {0}'
                              .format(delete_resp.status_code))

    def test_delete_already_deleted_group(self):
        """
        Verify delete group with an already deleted group returns 404.
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create failed with {0}'
                              .format(create_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.validate_headers(delete_resp.headers)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete failed with {0}'
                              .format(delete_resp.status_code))
        delete_resp = self.autoscale_client.delete_scaling_group(group.id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete failed with {0}'
                              .format(delete_resp.status_code))
