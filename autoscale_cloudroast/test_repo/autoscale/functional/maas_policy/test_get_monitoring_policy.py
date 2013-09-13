"""
Test to get and verify a cloud monitoring policy
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class GetMaasScalingPolicy(ScalingGroupFixture):

    """
    Verify delete cloud monitoring policy
    """

    def setUp(self):
        """
        Create a monitoring scaling policy
        """
        super(GetMaasScalingPolicy, self).setUp()
        self.policy = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id)

    def test_get_monitoring_policy(self):
        """
        Get the monitoring policy and verify the response code, response and headers
        """
        get_policy_response = self.autoscale_client.delete_scaling_policy(
            self.group.id,
            self.policy['id'])
        self.assertEqual(get_policy_response.status_code, 200,
                         msg=('Get monitoring policy was unsuccessful and resulted in {0}'
                              'for group {1}').format(get_policy_response.status_code,
                                                      self.group.id))

        self.validate_headers(get_policy_response['headers'])
        get_maas_policy = get_policy_response.entity
        self.assertTrue(get_maas_policy.id is not None,
                        msg='monitoring scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(get_maas_policy.links is not None,
                        msg="Newly created monitoring scaling policy's links are null for "
                        'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.cooldown, self.sp_cooldown,
                          msg="monitoring scaling policy's cooldown time does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.change, self.sp_change,
                          msg="monitoring scaling policy's change does not match  for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.type, 'cloud_monitoring',
                          msg="monitoring scaling policy's type is not cloud_monitoring for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.check.type, self.check_type,
                          msg="monitoring scaling policy's check type does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.check.label, self.check_label,
                          msg="monitoring scaling policy's check label does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.check.period, self.check_period,
                          msg="monitoring scaling policy's check metadata does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.check.timeout, self.check_timeout,
                          msg="monitoring scaling policy's check timeout does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(
            get_maas_policy.check.monitoring_zones_poll, self.monitoring_zones,
            msg="monitoring scaling policy's monitoring zones does not match for "
            'group {0}'.format(self.group.id))
        self.assertEquals(get_maas_policy.target_alias, self.target_alias,
                          msg="monitoring scaling policy's target hostname does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(
            get_maas_policy.alarm_criteria.criteria, self.alarm_criteria,
            msg="monitoring scaling policy's alarm criteria does not match for "
            'group {0}'.format(self.group.id))
