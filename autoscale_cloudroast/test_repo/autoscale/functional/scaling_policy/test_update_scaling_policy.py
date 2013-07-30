"""
Test to update and verify the updated policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class UpdateScalingPolicy(ScalingGroupPolicyFixture):
    """
    Verify update policy
    """

    @classmethod
    def setUpClass(cls):
        """
        Creates a scaling group with policy with type change
        """
        super(UpdateScalingPolicy, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Deletes the scaling group
        """
        super(UpdateScalingPolicy, cls).tearDownClass()

    def test_update_change_scaling_policy(self):
        """
        Verify the update policy call by updating the exiting change
        and verify the response code 204, headers and data
        """
        update_policy_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            name=self.policy['name'],
            cooldown=self.policy['cooldown'],
            change=self.upd_sp_change,
            policy_type=self.sp_policy_type)
        policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.policy['id'])
        updated_policy = policy_response.entity
        self.assertEquals(update_policy_response.status_code, 204,
                          msg='Update scaling policy failed with {0}'
                          .format(update_policy_response.status_code))
        self.validate_headers(update_policy_response.headers)
        self.assertEquals(updated_policy.id, self.policy['id'],
                          msg='Policy Id is not as expected after update')
        self.assertEquals(updated_policy.links, self.policy['links'],
                          msg='Links for the scaling policy is none after the update')
        self.assertEquals(updated_policy.name, self.policy['name'],
                          msg='Name of the policy is None after update')
        self.assertEquals(
            updated_policy.cooldown, self.policy['cooldown'],
            msg='Cooldown of the policy in null after an update')
        self.assertEquals(updated_policy.change, self.upd_sp_change,
                          msg='Change in the policy did not update')

    def test_update_to_desiredcapacity_scaling_policy(self):
        """
        Verify the update policy call by updating change to be desired capacity
        and verify the response code 204, headers and data
        """
        update_policy_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            name=self.policy['name'],
            cooldown=self.policy['cooldown'],
            desired_capacity=self.sp_desired_capacity,
            policy_type=self.sp_policy_type)
        policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.policy['id'])
        updated_policy = policy_response.entity
        self.assertEquals(update_policy_response.status_code, 204,
                          msg='Update scaling policy failed with {0}'
                          .format(update_policy_response.status_code))
        self.validate_headers(update_policy_response.headers)
        self.assertEquals(updated_policy.id, self.policy['id'],
                          msg='Policy Id is not as expected after update')
        self.assertEquals(updated_policy.links, self.policy['links'],
                          msg='Links for the scaling policy is none after the update')
        self.assertEquals(updated_policy.name, self.policy['name'],
                          msg='Name of the policy is None after update')
        self.assertEquals(
            updated_policy.cooldown, self.policy['cooldown'],
            msg='Cooldown of the policy in null after an update')
        self.assertEquals(updated_policy.desiredCapacity, self.sp_desired_capacity,
                          msg='Change in the policy did not update')
