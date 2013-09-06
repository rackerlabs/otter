"""
Test to create and verify a cloyd monitoring policy
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class CreateMaasScalingPolicy(ScalingGroupFixture):
    """
    Verify create cloud monitoring policy
    """

    def test_create_cloud_monitoring_scaling_policy(self):
        """
        Create a scaling policy of type cloud_montoring,
        verify reponse code 201, headers and data.
        """
        check_disabled = False
        check_metadata = {'monitoring': 'autoscale'}
        target_hostname = '10.200.100.19'
        target_resolver = 'IPv4'
        monitoring_policy = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id, check_disabled=check_disabled,
            check_metadata=check_metadata,
            target_hostname=target_hostname, target_resolver=target_resolver)
        self.assertEquals(monitoring_policy['status_code'], 201,
                          msg='Create schedule scaling policy failed with {0} for group {1}'
                          .format(monitoring_policy['status_code'], self.group.id))
        self.validate_headers(monitoring_policy['headers'])
        self.assertTrue(monitoring_policy['id'] is not None,
                        msg='monitoring scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(monitoring_policy['links'] is not None,
                        msg="Newly created monitoring scaling policy's links are null for group "
                        '{0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['cooldown'], self.sp_cooldown,
                          msg="monitoring scaling policy's cooldown time does not match for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['change'], self.sp_change,
                          msg="monitoring scaling policy's change does not match  for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['type'], 'cloud_monitoring',
                          msg="monitoring scaling policy's type is not cloud_monitoring for group "
                          '{0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_type'], self.check_type,
                          msg="monitoring scaling policy's check type does not match for group  "
                          '{0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_type'], self.check_type,
                          msg="monitoring scaling policy's check type does not match for group "
                          '{0}'.format(self.group.id))
