"""
Test to create and verify the created policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class CreateScalingPolicy(ScalingGroupPolicyFixture):

    """
    Verify create policy.
    """

    def test_create_scaling_policy(self):
        """
        Verify the create policy call for response code 201, headers and data.
        """
        self.assertEquals(self.create_policy_response.status_code, 201,
                          msg='Create scaling policy failed with {0} for group'
                          ' {1}'.format(self.group.id,
                                        self.create_policy_response.status_code))
        self.validate_headers(self.create_policy_response.headers)
        self.assertTrue(self.policy['id'] is not None,
                        msg='Scaling policy id is None for group'
                        ' {0}'.format(self.group.id))
        self.assertTrue(self.policy['links'] is not None,
                        msg="Newly created scaling policy's links are null for group"
                        " {0}".format(self.group.id))
        self.assertEquals(self.policy['cooldown'], self.sp_cooldown,
                          msg="scaling policy's cooldown time does not match for group"
                          " {0}".format(self.group.id))
        self.assertEquals(self.policy['change'], self.sp_change,
                          msg="Scaling policy's change does not match for group"
                          " {0}".format(self.group.id))
        self.assertEquals(self.policy['name'], self.sp_name,
                          msg="Scaling policy's name does not match for group"
                          " {0}".format(self.group.id))
        self.assertEquals(self.policy['count'], 1,
                          msg='More scaling policies listed than created for group'
                          ' {0}'.format(self.group.id))
