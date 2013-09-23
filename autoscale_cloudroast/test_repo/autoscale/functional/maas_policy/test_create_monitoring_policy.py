"""
Test to create and verify a cloud monitoring policy
"""
import unittest

from test_repo.autoscale.fixtures import ScalingGroupFixture
from cloudcafe.common.tools.datagen import rand_name


@unittest.skip('Not yet implemented')
class CreateMaasScalingPolicy(ScalingGroupFixture):
    """
    Verify create cloud monitoring policy
    """

    def test_create_cloud_monitoring_scaling_policy_with_http_check(self):
        """
        Create a scaling policy of type cloud_montoring,
        verify response code 201, headers and data.
        """
        check_disabled = False
        check_metadata = {'monitoring': 'autoscale'}
        check_type = 'remote.http'
        target_hostname = '10.200.100.19'
        sp_name = rand_name('create_maas_policy')
        target_resolver = 'IPv4'
        check_url = self.check_url
        check_method = self.check_method
        monitoring_policy = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id, check_disabled=check_disabled,
            check_url=check_url, check_method=check_method,
            check_metadata=check_metadata, sp_name=sp_name,
            target_hostname=target_hostname, target_resolver=target_resolver,
            check_type=check_type)
        self.assertEquals(monitoring_policy['status_code'], 201,
                          msg='Create schedule scaling policy failed with {0} for group '
                          '{1}'.format(monitoring_policy['status_code'], self.group.id))
        self.validate_headers(monitoring_policy['headers'])
        self.assertTrue(monitoring_policy['id'] is not None,
                        msg='monitoring scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(monitoring_policy['links'] is not None,
                        msg="Newly created monitoring scaling policy's links are null for "
                        'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['name'], sp_name,
                          msg="monitoring scaling policy's name does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['cooldown'], self.sp_cooldown,
                          msg="monitoring scaling policy's cooldown time does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['change'], self.sp_change,
                          msg="monitoring scaling policy's change does not match  for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['type'], 'cloud_monitoring',
                          msg="monitoring scaling policy's type is not cloud_monitoring for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_type'], check_type,
                          msg="monitoring scaling policy's check type does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_label'], self.check_label,
                          msg="monitoring scaling policy's check label does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_disabled'], check_disabled,
                          msg="monitoring scaling policy's check disabled does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_metadata'], check_metadata,
                          msg="monitoring scaling policy's check metadata does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_period'], self.check_period,
                          msg="monitoring scaling policy's check metadata does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_timeout'], self.check_timeout,
                          msg="monitoring scaling policy's check timeout does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['monitoring_zones'], self.monitoring_zones,
                          msg="monitoring scaling policy's monitoring zones does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['target_hostname'], self.target_hostname,
                          msg="monitoring scaling policy's target hostname does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['target_resolver'], self.target_resolver,
                          msg="monitoring scaling policy's target resolver does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['alarm_criteria'], self.alarm_criteria,
                          msg="monitoring scaling policy's alarm criteria does not match for "
                          'group {0}'.format(self.group.id))

    def test_create_cloud_monitoring_scaling_policy_with_ping_check(self):
        """
        Create a scaling policy of type cloud_montoring,
        verify response code 201, headers and data.
        TODO : validate the ping check json.
        """
        check_type = 'remote.ping'
        check_disabled = False
        sp_name = rand_name('test-ping-check-policy')
        check_metadata = {'monitoring': 'autoscale'}
        target_alias = 'default'
        monitoring_policy = self.autoscale_behaviors.create_monitoring_policy_given(
            group_id=self.group.id, check_type=check_type, check_disabled=check_disabled,
            check_metadata=check_metadata, target_alias=target_alias)
        self.assertEquals(monitoring_policy['status_code'], 201,
                          msg='Create schedule scaling policy failed with {0} for group '
                          '{1}'.format(monitoring_policy['status_code'], self.group.id))
        self.validate_headers(monitoring_policy['headers'])
        self.assertTrue(monitoring_policy['id'] is not None,
                        msg='monitoring scaling policy id is None for group '
                        '{0}'.format(self.group.id))
        self.assertTrue(monitoring_policy['links'] is not None,
                        msg="Newly created monitoring scaling policy's links are null for "
                        'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['name'], sp_name,
                          msg="monitoring scaling policy's name does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['cooldown'], self.sp_cooldown,
                          msg="monitoring scaling policy's cooldown time does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['change'], self.sp_change,
                          msg="monitoring scaling policy's change does not match  for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['type'], 'cloud_monitoring',
                          msg="monitoring scaling policy's type is not cloud_monitoring for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_type'], check_type,
                          msg="monitoring scaling policy's check type does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_label'], self.check_label,
                          msg="monitoring scaling policy's check label does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_disabled'], check_disabled,
                          msg="monitoring scaling policy's check disabled does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_metadata'], check_metadata,
                          msg="monitoring scaling policy's check metadata does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_period'], self.check_period,
                          msg="monitoring scaling policy's check metadata does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['check_timeout'], self.check_timeout,
                          msg="monitoring scaling policy's check timeout does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['monitoring_zones'], self.monitoring_zones,
                          msg="monitoring scaling policy's monitoring zones does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['target_alias'], target_alias,
                          msg="monitoring scaling policy's target hostname does not match for "
                          'group {0}'.format(self.group.id))
        self.assertEquals(monitoring_policy['alarm_criteria'], self.alarm_criteria,
                          msg="monitoring scaling policy's alarm criteria does not match for "
                          'group {0}'.format(self.group.id))
