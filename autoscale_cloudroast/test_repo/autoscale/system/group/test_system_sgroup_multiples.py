"""
System tests for account with multiple scaling groups
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags
import time

import unittest


class ScalingGroupMultiplesTest(AutoscaleFixture):

    """
    System tests to verify multiple groups on an account
    """

    def setUp(self):
        """
        Create 3 scaling groups
        """
        super(ScalingGroupMultiplesTest, self).setUp()
        first_group = self.autoscale_behaviors.create_scaling_group_given(
            gc_cooldown=0)
        self.first_scaling_group = first_group.entity
        self.resources.add(self.first_scaling_group, self.empty_scaling_group)

    @tags(speed='quick')
    def test_system_create_group_with_multiple_policies(self):
        """
        Scaling group can have multiple policies and can be executed
        """
        change = 3
        percentage = 50
        cooldown = 0
        policy1 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change=change,
            sp_cooldown=cooldown)
        policy2 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        policy3 = self.autoscale_behaviors.create_policy_given(
            group_id=self.first_scaling_group.id,
            sp_change_percent=percentage,
            sp_cooldown=cooldown)
        for each in [policy1, policy2, policy3]:
            execute_policies = self.autoscale_client.execute_policy(
                self.first_scaling_group.id, each['id'])
            self.assertEquals(execute_policies.status_code, 202,
                              msg='Policy execution failed for group {0} with '
                              '{1}'.format(self.first_scaling_group.id, execute_policies.status_code))
        sp1 = self.gc_min_entities + change
        sp2 = self.autoscale_behaviors.calculate_servers(sp1, percentage)
        sp3 = self.autoscale_behaviors.calculate_servers(sp2, percentage)
        self.verify_group_state(self.first_scaling_group.id, sp3)

    @tags(speed='quick')
    def test_system_create_policy_with_multiple_webhooks(self):
        """
        Scaling policy in a group can have multiple webhooks and they can be
        executed
        """

        policy = self.autoscale_behaviors.create_policy_min(
            group_id=self.first_scaling_group.id,
            sp_cooldown=0)
        webhook_first = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook1')
        webhook_one = self.autoscale_behaviors.get_webhooks_properties(
            webhook_first.entity)
        webhook_second = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook2')
        webhook_two = self.autoscale_behaviors.get_webhooks_properties(
            webhook_second.entity)
        webhook_third = self.autoscale_client.create_webhook(
            group_id=self.first_scaling_group.id,
            policy_id=policy['id'],
            name='testwebhook3')
        webhook_three = self.autoscale_behaviors.get_webhooks_properties(
            webhook_third.entity)
        for each_webhook in [webhook_one, webhook_two, webhook_three]:
            execute_webhook = self.autoscale_client.execute_webhook(
                each_webhook['links'].capability)
            self.assertEquals(execute_webhook.status_code, 202,
                              msg='Policy webhook execution failed for group {0} with '
                              '{1}'.format(self.first_scaling_group.id, execute_webhook.status_code))
        time.sleep(10)
        self.verify_group_state(
            self.first_scaling_group.id, (self.sp_change * 3))

    @tags(type='one-time')
    def test_system_max_scaling_groups_on_one_account(self):
        """
        The maximum scaling groups an account cannot be more than 1000.
        Trying to create groups beyond max results in 422.
        """
        current_group_count = self.get_total_num_groups()
        max_groups = self.max_groups - current_group_count
        for _ in (range(max_groups)):
            create_group_reponse = self.autoscale_behaviors.create_scaling_group_min()
            self.assertEquals(create_group_reponse.status_code, 201, msg='{0}'
                              'groups exist already'.format(self.get_total_num_groups()))
            self.resources.add(create_group_reponse.entity, self.empty_scaling_group)
        self.assertEquals(self.get_total_num_groups(), self.max_groups, msg='{0} groups'
                          'exist'.format(self.get_total_num_groups()))
        create_group_beyond_max = self.autoscale_behaviors.create_scaling_group_min()
        self.assertEquals(create_group_beyond_max.status_code, 422,
                          msg='{0} groups exist on the tenant'.format(self.get_total_num_groups()))

    @unittest.skip('Not yet implemented')
    @tags(type='one-time')
    def test_system_max_webhook_policies_on_a_scaling_group(self):
        """
        Verify maximum scaling policies are allowed on a scaling group.
        Trying to create policies beyond max results in 422
        """
        for policy in (range(self.max_policies)):
            self.autoscale_behaviors.create_policy_min(self.first_scaling_group.id)
        self.assertEquals(self.get_total_num_policies(self.first_scaling_group.id),
                          self.max_policies)
        policy_beyond_max = self.autoscale_behaviors.create_policy_min(
            self.first_scaling_group.id)
        self.assertEquals(policy_beyond_max['status_code'], 422,
                          msg='Created {0} policies on the '
                          'group'.format(self.get_total_num_policies(
                                         self.first_scaling_group.id)))

    @unittest.skip('Not yet implemented')
    @tags(type='one-time')
    def test_system_max_scheduler_policies_on_a_scaling_group(self):
        """
        Verify maximum scaling policies are allowed on a scaling group.
        Trying to create policies beyond max results in 422.
        """
        for _ in (range(self.max_policies)):
            self.autoscale_behaviors.create_schedule_policy_given(
                self.first_scaling_group.id,
                sp_change_percent=100)
        self.assertEquals(self.get_total_num_policies(self.first_scaling_group.id),
                          self.max_policies,
                          msg='Policies on the group {0} is under/over max '
                          'allowed'.format(self.first_scaling_group.id))
        policy_beyond_max = self.autoscale_behaviors.create_schedule_policy_given(
            self.first_scaling_group.id,
            sp_change_percent=100)
        self.assertEquals(policy_beyond_max['status_code'], 422,
                          msg='Created {0} policies on the '
                          'group'.format(self.get_total_num_policies(
                                         self.first_scaling_group.id)))

    @unittest.skip('Not yet implemented')
    @tags(type='one-time')
    def test_system_max_webhooks_on_a_scaling_policy(self):
        """
        Verify the maximum scaling policies are allowed on a scaling policy.
        Trying to create webhooks beyond max results in 422
        """
        policy = self.autoscale_behaviors.create_policy_min(self.first_scaling_group.id)
        for webhook in (range(self.max_webhooks)):
            self.autoscale_client.create_webhook(self.first_scaling_group.id,
                                                 policy['id'], 'wb_{0}'.format(webhook))
        self.assertEquals(self.get_total_num_webhooks(self.first_scaling_group.id, policy['id']),
                          self.max_webhooks,
                          msg='Webhooks on the group {0} is under/over max allowed for policy '
                          '{1}'.format(self.first_scaling_group.id, policy['id']))
        webhook_beyond_max = self.autoscale_client.create_webhook(self.first_scaling_group.id,
                                                                  policy['id'],
                                                                  'wb_{0}'.format(webhook))
        self.assertEquals(webhook_beyond_max.status_code, 422,
                          msg='Created {0} webhooks on the '
                          'policy'.format(self.get_total_num_webhooks(self.first_scaling_group.id,
                                          policy['id'])))
