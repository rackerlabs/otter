"""
Test negative scenarios for a scaling group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from autoscale.status_codes import HttpStatusCodes


class ScalingGroupNegative(AutoscaleFixture):

    """
    Verify negative scenarios for scaling group.
    """
    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(ScalingGroupNegative, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(ScalingGroupNegative, cls).tearDownClass()

    # @unittest.skip('invalid when tests are running in parallel and on a tenant that has groups')
    # def test_list_scaling_group_when_none_exist(self):
    #     """
    #     Negative test: List scaling groups when none exists on the account.
    #     (also helps validate that teardowns within the testsuite )
    #     """
    #     list_groups_resp = self.autoscale_client.list_scaling_groups()
    #     list_groups = list_groups_resp.entity
    #     self.assertEquals(list_groups_resp.status_code, 200,
    #                       msg='The list group call when no groups exists failed with %s'
    #                       % list_groups_resp.status_code)
    #     self.validate_headers(list_groups_resp.headers)
    #     self.assertEquals(list_groups, [],
    #                       msg='Some scaling groups exist on the account')

    def test_scaling_group_name_blank(self):
        """
        Negative Test: Scaling group should not get created with an empty
        group configuration name
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_name='')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_name_whitespace(self):
        """
        Negative Test: Scaling group should not get created with group
        configuration name as only whitespace
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_name=' ')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_minentities_lessthan_zero(self):
        """
        Negative Test: Scaling group should not get created when min entities
        are less than Zero
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities='-100')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_maxentities_lessthan_zero(self):
        """
        Negative Test: Scaling group should not get created when max entities
        are less than Zero
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_max_entities='-0.01')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_maxentities_over_25(self):
        """
        Negative Test: Scaling group should not get created when max entities
        are over 25
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_max_entities='25.9')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_cooldown_lessthan_zero(self):
        """
        Negative Test: Scaling group should not get created when cooldown
        is less than Zero
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown='-0.08')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling group with invalid request returned: %s'
                        % create_error)

    def test_scaling_group_minentities_max(self):
        """
        Negative Test: Scaling group should not get created when min entities are max
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        gc_min_entities = 26
        create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=gc_min_entities)
        self.assertEquals(create_resp.status_code, expected_status_code,
                          msg='Create scaling group passed with max minentities. Response: %s'
                          % create_resp.status_code)

    def test_create_scaling_group_minentities_over_max(self):
        """
        Negative Test: Scaling group should not get created when min entities are over max
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        gc_min_entities = 22
        gc_max_entities = 2
        create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=gc_min_entities,
            gc_max_entities=gc_max_entities)
        self.assertEquals(create_resp.status_code, expected_status_code,
                          msg='Create scaling group passed with max < minentities. Response: %s'
                          % create_resp.status_code)

    def test_scaling_group_maxentities_max(self):
        """
        Negative Test: Scaling group should not get created when max entities
        is over 25
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        gc_max_entities = 26
        create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_max_entities=gc_max_entities)
        self.assertEquals(create_resp.status_code, expected_status_code,
                          msg='Create group passed when maxntities is over 25 with response: %s'
                          % create_resp.status_code)

    def test_scaling_group_with_max_cooldown(self):
        """
        Negative Test: Scaling group should not get created when cooldown
        is over 86400 seconds (24 hrs)
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        gc_cooldown = 86401
        create_resp = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=gc_cooldown)
        self.assertEquals(create_resp.status_code, expected_status_code,
                          msg='Create group passed when cooldown is over 24 hrs with response: %s'
                          % create_resp.status_code)

    def test_get_invalid_group_id(self):
        """
        Negative Test: Get group with invalid group id should fail with
        resource not found 404
        """
        group = 13344
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.view_manifest_config_for_scaling_group(
            group_id=group)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create group with invalid request returned: %s'
                        % create_error)

    def test_update_invalid_group_id(self):
        """
        Negative Test: Update group with invalid group id should fail with
        resource not found 404
        """
        group = gc_max_entities = 25
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_group_config(
            group_id=group,
            name=self.gc_name,
            cooldown=self.gc_cooldown,
            min_entities=self.gc_min_entities,
            max_entities=gc_max_entities,
            metadata={})
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create group with invalid request returned: %s'
                        % create_error)

    def test_get_group_after_deletion(self):
        """
        Negative Test: Get group when group is deleted should fail with 404
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        del_resp = self.autoscale_client.delete_scaling_group(
            group_id=group.id)
        self.assertEquals(
            create_resp.status_code, 201, msg='create group failed')
        self.assertEquals(del_resp.status_code, 204, msg='Delete group failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.view_manifest_config_for_scaling_group(
            group_id=group.id)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create group succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create group with invalid request returned: %s'
                        % create_error)

    def test_update_group_after_deletion(self):
        """
        Negative Test: Trying to update group when group is deleted should fail with 404
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        del_resp = self.autoscale_client.delete_scaling_group(
            group_id=group.id)
        self.assertEquals(
            create_resp.status_code, 201, msg='create group failed')
        self.assertEquals(del_resp.status_code, 204, msg='Delete group failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=self.gc_name,
            cooldown=90,
            min_entities=self.gc_min_entities,
            max_entities=group.groupConfiguration.maxEntities,
            metadata={})
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create group succeeded with invalid request: %s, groupid: %s'
                          % (error_create_resp.status_code, group.id))
        self.assertTrue(create_error is None,
                        msg='Create group with invalid request returned: %s'
                        % create_error)
