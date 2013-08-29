"""
Test to create and verify delete group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteScalingGroupTest(AutoscaleFixture):

    """
    Verify delete group.
    """

    def setUp(self):
        """
        create a scaling group
        """
        super(DeleteScalingGroupTest, self).setUp()
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        self.group = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='The create resulted in {0} for group '
                          '{1}'.format(create_resp.status_code, self.group))

    def test_delete_group_with_0_minentities(self):
        """
        Verify delete group returns response code 204 when group has 0 min entities.
        """
        delete_resp = self.autoscale_client.delete_scaling_group(self.group.id)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete resulted in {0} for group '
                              '{1}'.format(delete_resp.status_code, self.group.id))

    def test_delete_invalid_groupid(self):
        """
        Verify delete group with invalid group id returns 404.
        """
        group_id = 'xyz'
        delete_resp = self.autoscale_client.delete_scaling_group(group_id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete resulted in {0} for an invalid group'
                              ' id'.format(delete_resp.status_code))

    def test_delete_already_deleted_group(self):
        """
        Verify delete group with an already deleted group returns 404.
        """
        delete_resp = self.autoscale_client.delete_scaling_group(self.group.id)
        self.validate_headers(delete_resp.headers)
        self.assertEquals(delete_resp.status_code, 204,
                          msg='The delete resulted in {0} for group'
                              '{1}'.format(delete_resp.status_code, self.group.id))
        delete_resp = self.autoscale_client.delete_scaling_group(self.group.id)
        self.assertEquals(delete_resp.status_code, 404,
                          msg='The delete on a deleted group succeeded with {0} for group'
                              '{1}'.format(delete_resp.status_code, self.group.id))
