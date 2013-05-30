"""
Test to negative scenarios for a scaling policy.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from autoscale.status_codes import HttpStatusCodes
import sys


class ScalingPolicyNegative(AutoscaleFixture):
    """
    Verify negative scenarios for a scaling policy
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(ScalingPolicyNegative, cls).setUpClass()
        cls.negative_num = -0.1
        create_resp = cls.autoscale_behaviors.create_scaling_group_min()
        cls.group = create_resp.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(ScalingPolicyNegative, cls).tearDownClass()

    def test_scaling_policy_nonexistant(self):
        """
        Negative Test: Verify for scaling policy on a newly created group
        """
        create_resp = self.autoscale_behaviors.create_scaling_group_min()
        group = create_resp.entity
        self.resources.add(group.id,
                           self.autoscale_client.delete_scaling_group)
        list_policy_resp = self.autoscale_client.list_policies(group.id)
        list_policy = list_policy_resp.entity
        self.assertEquals(list_policy_resp.status_code, 200,
                          msg='List scaling policies failed with %s'
                          % list_policy_resp.status_code)
        self.validate_headers(list_policy_resp.headers)
        self.assertEquals(list_policy, [],
                          msg='Some scaling policies exist on the scaling group')

    def test_scaling_policy_name_blank(self):
        """
        Negative Test: Scaling policy should not get created with an empty name.
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name='',
                                                                cooldown=self.sp_cooldown,
                                                                change=self.sp_change,
                                                                policy_type=self.sp_policy_type)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling policy succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling policy with invalid request returned: %s'
                        % create_error)

    def test_scaling_policy_name_whitespace(self):
        """
        Negative Test: Scaling policy should not get created with name as whitespace.
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name='  ',
                                                                cooldown=self.sp_cooldown,
                                                                change=self.sp_change,
                                                                policy_type=self.sp_policy_type)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling policy succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling policy with invalid request returned: %s'
                        % create_error)

    def test_scaling_policy_cooldown_lessthan_zero(self):
        """
        Negative Test: Scaling policy should not get created with
        cooldown less than zero.
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name=self.sp_name,
                                                                cooldown='-00.01',
                                                                change=self.sp_change,
                                                                policy_type=self.sp_policy_type)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling policy succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling policy with invalid request returned: %s'
                        % create_error)

    def test_scaling_policy_change_lessthan_zero(self):
        """
        Negative Test: Scaling policy should not get created with change less than zero
        """
        expected_status_code = HttpStatusCodes.BAD_REQUEST
        error_create_resp = self.autoscale_client.create_policy(group_id=self.group.id,
                                                                name=self.sp_name,
                                                                cooldown=self.sp_cooldown,
                                                                change='0.001')
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create scaling policy succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create scaling policy with invalid request returned: %s'
                        % create_error)

    def test_get_invalid_policy_id(self):
        """
        Negative Test: Get policy with invalid policy id should fail with
        resource not found 404
        """
        policy = 13344
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.get_policy_details(group_id=self.group.id,
                                                                     policy_id=policy)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create policies succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create policies with invalid request returned: %s'
                        % create_error)

    def test_update_invalid_policy_id(self):
        """
        Negative Test: Update policy with invalid policy id should fail with
        resource not found 404
        """
        policy = 13344
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_policy(group_id=self.group.id,
                                                                policy_id=policy,
                                                                name=self.sp_name,
                                                                cooldown=self.sp_cooldown,
                                                                change=self.sp_change,
                                                                policy_type=self.sp_policy_type)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create policies succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create policies with invalid request returned: %s'
                        % create_error)

    def test_get_policy_after_deletion(self):
        """
        Negative Test: Get policy when policy is deleted should fail with
        resource not found 404
        """
        policy = self.autoscale_behaviors.create_policy_min(self.group.id)
        del_resp = self.autoscale_client.delete_scaling_policy(group_id=self.group.id,
                                                               policy_id=policy['id'])
        self.assertEquals(del_resp.status_code, 204, msg='Delete policy failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.get_policy_details(group_id=self.group.id,
                                                                     policy_id=policy['id'])
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create policies succeeded with invalid request: %s'
                          % error_create_resp.status_code)
        self.assertTrue(create_error is None,
                        msg='Create policies with invalid request returned: %s'
                        % create_error)

    def test_update_policy_after_deletion(self):
        """
        Negative Test: Update policy when policy is deleted should fail with
        resource not found 404
        """
        policy = self.autoscale_behaviors.create_policy_min(self.group.id)
        del_resp = self.autoscale_client.delete_scaling_policy(group_id=self.group.id,
                                                               policy_id=policy['id'])
        self.assertEquals(del_resp.status_code, 204, msg='Delete policy failed')
        expected_status_code = HttpStatusCodes.NOT_FOUND
        error_create_resp = self.autoscale_client.update_policy(group_id=self.group.id,
                                                                policy_id=policy['id'],
                                                                name=self.sp_name,
                                                                cooldown=self.sp_cooldown,
                                                                change=self.sp_change,
                                                                policy_type=self.sp_policy_type)
        create_error = error_create_resp.entity
        self.assertEquals(error_create_resp.status_code, expected_status_code,
                          msg='Create policies succeeded with invalid request: %s, policy/groupid: %s %s'
                          % (error_create_resp.status_code, self.group.id, policy['id']))
        self.assertTrue(create_error is None,
                        msg='Create policies with invalid request returned: %s'
                        % create_error)

    def test_scaling_policy_maxint_cooldown_change(self):
        """
        Negative Test: Test scaling policy when change and cooldown are maxint
        """
        cooldown = change = sys.maxint
        create_resp = self.autoscale_client.create_policy(
            group_id=self.group.id,
            name=self.sp_name,
            cooldown=cooldown,
            change=change,
            policy_type=self.sp_policy_type)
        policy = create_resp.entity
        self.assertEquals(create_resp.status_code, 201,
                          msg='Create scaling policy failed with maxint as cooldown & change: %s'
                          % create_resp.status_code)
        self.assertTrue(policy is not None,
                        msg='Create scaling policy failed: %s'
                        % policy)
