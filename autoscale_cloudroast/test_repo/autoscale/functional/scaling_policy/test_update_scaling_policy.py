"""
Test to update and verify the updated policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class UpdateScalingPolicy(ScalingGroupPolicyFixture):

    """
    Verify update policy
    """

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
        self._assert_updated_policy(update_policy_response)

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
        self._assert_updated_policy(update_policy_response, 'desired_capacity')

    def test_update_to_changepercent_scaling_policy(self):
        """
        Verify the update policy call by updating change to be change percent
        and verify the response code 204, headers and data
        """
        update_policy_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.policy['id'],
            name=self.policy['name'],
            cooldown=self.policy['cooldown'],
            change_percent=self.sp_change_percent,
            policy_type=self.sp_policy_type)
        self._assert_updated_policy(update_policy_response, 'change_percent')

    def _assert_updated_policy(self, update_policy_response,
                               policy_change_type='change'):
        """
        Assert update policy is as expected
        """
        policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.policy['id'])
        updated_policy = policy_response.entity
        self.assertEquals(update_policy_response.status_code, 204,
                          msg='Update scaling policy failed with {0} for group'
                          ' {1}'.format(update_policy_response.status_code,
                                        self.group.id))
        self.validate_headers(update_policy_response.headers)
        self.assertEquals(updated_policy.id, self.policy['id'],
                          msg='Policy Id is not as expected after update '
                          'for group {0}'.format(self.group.id))
        self.assertEquals(updated_policy.links, self.policy['links'],
                          msg='Links for the scaling policy is none after the update '
                          'for group {0}'.format(self.group.id))
        self.assertEquals(updated_policy.name, self.policy['name'],
                          msg='Name of the policy is None after update '
                          'for group {0}'.format(self.group.id))
        self.assertEquals(
            updated_policy.cooldown, self.policy['cooldown'],
            msg='Cooldown of the policy in null after an update '
            'for group {0}'.format(self.group.id))
        if policy_change_type is 'desired_capacity':
            self.assertEquals(
                updated_policy.desiredCapacity, self.sp_desired_capacity,
                msg='Desired capacity in the policy did not update '
                'for group {0}'.format(self.group.id))
        if policy_change_type is 'change_percent':
            self.assertEquals(
                updated_policy.changePercent, self.sp_change_percent,
                msg='Change Percent in the policy did not update '
                'for group {0}'.format(self.group.id))
        if policy_change_type is 'change':
            self.assertEquals(
                updated_policy.change, self.upd_sp_change,
                msg='Change in the policy did not update '
                'for group {0}'.format(self.group.id))
