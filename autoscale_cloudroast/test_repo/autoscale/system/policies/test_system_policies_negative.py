"""
System tests for scaling policies negative scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cafe.drivers.unittest.decorators import tags


class ScalingPoliciesNegativeFixture(AutoscaleFixture):

    """
    System tests to verify execute scaling policies scenarios
    """

    def setUp(self):
        """
        Create a scaling group with minentities = maxentities, scale up by 2
        """
        super(ScalingPoliciesNegativeFixture, self).setUp()
        self.create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=2,
            gc_cooldown=0)
        self.group = self.create_group_response.entity
        self.policy_up_data = {'change': 2}
        self.policy_up = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_up_data,
            execute_policy=False)
        self.policy_down_data = {'change': -2}
        self.policy_down = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=self.policy_down_data,
            execute_policy=False)
        self.resources.add(self.group, self.empty_scaling_group)

    @tags(speed='quick')
    def test_system_execute_policy_when_maxentities_equals_minentities(self):
        """
        Update minentities=maxentities and execution of a scale up policy
        fails with a 403
        """
        self._update_group_min_max_entities(group=self.group,
                                            maxentities=self.group.groupConfiguration.minEntities)
        execute_policy_up = self.autoscale_client.execute_policy(self.group.id,
                                                                 self.policy_up['policy_id'])
        self.assertEquals(execute_policy_up.status_code, 403,
                          msg='Scale up policy executed when minentities=maxentities: {0} for group {1}'
                          .format(execute_policy_up.status_code, self.group.id))

    @tags(speed='quick')
    def test_system_execute_scale_down_on_newly_created_group_with_minentities(self):
        """
        Update minentities=maxentities and execution of a scale down policy
        fails with a 403
        """
        self._update_group_min_max_entities(group=self.group,
                                            maxentities=self.group.groupConfiguration.minEntities)
        execute_policy_down = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_down['policy_id'])
        self.assertEquals(execute_policy_down.status_code, 403,
                          msg='Scale down policy executed when minentities=maxentities'
                          ' on the group {0} with response code {1}'
                          .format(self.group.id, execute_policy_down.status_code))

    @tags(speed='quick')
    def test_system_delete_policy_during_execution(self):
        """
        Policy execution is not affected/paused when the policy is deleted during execution.
        (Also, verify if otter refers to the policy id after it has executed the policy and
        raises exception.)
        """
        execute_policy_up = self.autoscale_client.execute_policy(self.group.id,
                                                                 self.policy_up['policy_id'])
        delete_policy = self.autoscale_client.delete_scaling_policy(
            self.group.id,
            self.policy_up['policy_id'])
        self.assertEquals(delete_policy.status_code, 204,
                          msg='Deleting the scaling policy while its executing failed {0}'
                          ' for group {1}'
                          .format(delete_policy.status_code, self.group.id))
        self.assertEquals(execute_policy_up.status_code, 202,
                          msg='Scale up policy failed for group {0} cause policy was deleted'
                          ' during execution: {1}'
                          .format(self.group.id, execute_policy_up.status_code))
        self.check_for_expected_number_of_building_servers(
            group_id=self.group.id,
            expected_servers=self.group.groupConfiguration.minEntities +
            self.policy_up_data['change'])

    @tags(speed='quick')
    def test_system_execute_scale_up_after_maxentities_met(self):
        """
        Update max entities of the scaling group to be 3 and execute scale up policy
        once to update active servers = maxentities successfully and reexecuting the
        policy when max entities are already met fails with 403
        """
        upd_maxentities = 3
        self._update_group_min_max_entities(group=self.group,
                                            maxentities=upd_maxentities)
        change_num = upd_maxentities - \
            self.group.groupConfiguration.minEntities
        policy_up = {'change': change_num, 'cooldown': 0}
        execute_policy = self.autoscale_behaviors.create_policy_webhook(
            group_id=self.group.id,
            policy_data=policy_up,
            execute_policy=True)
        self.assertEquals(execute_policy['execute_response'], 202,
                          msg='Scale up policy execution failed for group {0}'
                          'when change delta < maxentities with response: {1}'
                          .format(self.group.id, execute_policy['execute_response']))
        reexecute_scale_up = self.autoscale_client.execute_policy(
            self.group.id,
            execute_policy['policy_id'])
        self.assertEquals(reexecute_scale_up.status_code, 403,
                          msg='Scale up policy executed for group {0} when group already'
                          ' has maxentities, response code: {1}'
                          .format(self.group.id, reexecute_scale_up.status_code))

    @tags(speed='slow')
    def test_system_scaleup_update_min_max_0_delete_group(self):
        """
        Create a scaling group and update min and max entities to be 0 and delete
        the group (while the servers from the create group are still building).
        The user will be able to delete the group and autoscaling will delete the
        servers on the group (AUTO-339)
        """
        server_name = self.group.launchConfiguration.server.name
        self._update_group_min_max_entities(group=self.group,
                                            maxentities=0, minentities=0)
        delete_group = self.autoscale_client.delete_scaling_group(
            self.group.id)
        self.assertEquals(delete_group.status_code, 204,
                          msg='Delete group failed for group {0} when min and maxentities '
                          'is update to 0 with response {1}'
                          .format(self.group.id, delete_group.status_code))
        self.assert_servers_deleted_successfully(server_name)

    @tags(speed='quick')
    def test_system_scaleup_update_min_scale_down(self):
        """
        Create a scaling group and execute a scale up policy, update min = current desired capacity.
        Then executing a scale down policy results in 403
        """
        execute_policy_up = self.autoscale_client.execute_policy(self.group.id,
                                                                 self.policy_up['policy_id'])
        self.assertEquals(execute_policy_up.status_code, 202,
                          msg='Scale up policy execution failed for group {0} '
                          'when change delta < maxentities with response: {1}'
                          .format(self.group.id, execute_policy_up.status_code))
        self._update_group_min_max_entities(group=self.group,
                                            minentities=self.group.groupConfiguration.minEntities +
                                            self.policy_up_data['change'])
        execute_policy_down = self.autoscale_client.execute_policy(
            self.group.id,
            self.policy_down['policy_id'])
        self.assertEquals(execute_policy_down.status_code, 403,
                          msg='Scale down policy executed when minentities=maxentities'
                          ' on the group {0} with response code {1}'
                          .format(self.group.id, execute_policy_down.status_code))

    @tags(speed='quick')
    def test_system_update_webhook_policy_to_at_style_scheduler(self):
        """
        Policy update fails when a webhook type policy is updated to be of type
        at style scheduler, with error 400
        """
        upd_policy_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.policy_up['policy_id'],
            name='upd_webhook_to_scheduler',
            cooldown=self.sp_cooldown,
            change=self.sp_change,
            args={'at': self.autoscale_behaviors.get_time_in_utc(60)},
            policy_type='schedule')
        self.assertEquals(upd_policy_response.status_code, 400,
                          msg='Update webhook policy to schedule policy type'
                          ' on the group {0} with response code {1}'.format(
                              self.group.id, upd_policy_response.status_code))

    @tags(speed='quick')
    def test_system_update_webhook_policy_to_cron_style_scheduler(self):
        """
        Policy update fails when a webhook type policy is updated to be of type
        cron style scheduler, with error 400
        """
        upd_policy_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.policy_down['policy_id'],
            name='upd_webhook_to_scheduler',
            cooldown=self.sp_cooldown,
            change=self.sp_change,
            args={'cron': '* 3 * * *'},
            policy_type='schedule')
        self.assertEquals(upd_policy_response.status_code, 400,
                          msg='Update webhook policy to schedule policy type'
                          ' on the group {0} with response code {1}'.format(
                              self.group.id, upd_policy_response.status_code))

    def _update_group_min_max_entities(self, group, maxentities=None, minentities=None):
        """
        Updates the scaling groups min/maxentities to the given and asserts the update
        was successful
        """
        if minentities is None:
            minentities = group.groupConfiguration.minEntities
        if maxentities is None:
            maxentities = group.groupConfiguration.maxEntities
        update_group = self.autoscale_client.update_group_config(
            group_id=group.id,
            name=group.groupConfiguration.name,
            cooldown=group.groupConfiguration.cooldown,
            min_entities=minentities,
            max_entities=maxentities,
            metadata={})
        self.assertEquals(update_group.status_code, 204,
                          msg='Updating minentities and/or maxentities in the group config'
                          ' for {0} failed: {1}'
                          .format(group.id, update_group.status_code))
