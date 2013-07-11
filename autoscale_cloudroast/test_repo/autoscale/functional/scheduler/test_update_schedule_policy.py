"""
Test to update and verify the updated scheduler policy.
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class UpdateSchedulerScalingPolicy(ScalingGroupFixture):

    """
    Verify update scheduler policy
    """

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        on a scaling group with 0 minentities
        """
        super(UpdateSchedulerScalingPolicy, self).setUp()
        self.at_value = self.autoscale_behaviors.get_time_in_utc(600)
        self.cron_value = '0 */10 * * *'
        self.at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_at=self.at_value)
        self.assertEquals(self.at_style_policy['status_code'], 201,
                          msg='Create schedule policy (at style) failed with {0} for group {1}'
                          .format(self.at_style_policy['status_code'], self.group.id))
        self.cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            sp_change=self.sp_change,
            schedule_cron=self.cron_value)
        self.assertEquals(self.cron_style_policy['status_code'], 201,
                          msg='Create schedule policy (cron style) failed with {0} for group {1}'
                          .format(self.cron_style_policy['status_code'], self.group.id))

    def test_update_at_style_scaling_policy(self):
        """
        Verify the update at style schedule policy by updating date
        and verify the response code 204, headers and data
        """
        upd_args = {'at': self.autoscale_behaviors.get_time_in_utc(6000)}
        updated_at_style_policy = self._update_policy(self.group.id,
                                                      self.at_style_policy,
                                                      upd_args)
        self.assertEquals(
            updated_at_style_policy.id, self.at_style_policy['id'],
            msg='Policy Id is not as expected after update')
        self.assertEquals(
            updated_at_style_policy.links, self.at_style_policy['links'],
            msg='Links for the scaling policy is none after the update')
        self.assertEquals(
            updated_at_style_policy.name, self.at_style_policy['name'],
            msg='Name of the policy is None after update')
        self.assertEquals(
            updated_at_style_policy.cooldown, self.at_style_policy['cooldown'],
            msg='Cooldown of the policy in null after an update')
        self.assertEquals(
            updated_at_style_policy.change, self.at_style_policy['change'],
            msg='Change in the policy is not as expected')
        self.assertEquals(updated_at_style_policy.args.at, upd_args['at'],
                          msg='At style schedule policy did not update for group {0}'
                          .format(self.group.id))

    def test_update_cron_style_scaling_policy(self):
        """
        Verify the update cron style schedule policy by updating date
        and verify the response code 204, headers and data
        """
        upd_args = {'cron': '0 0 * * 1'}
        updated_cron_style_policy = self._update_policy(self.group.id,
                                                        self.cron_style_policy,
                                                        upd_args)
        self.assertEquals(
            updated_cron_style_policy.id, self.cron_style_policy['id'],
            msg='Policy Id is not as expected after update')
        self.assertEquals(
            updated_cron_style_policy.links, self.cron_style_policy['links'],
            msg='Links for the scaling policy is none after the update')
        self.assertEquals(
            updated_cron_style_policy.name, self.cron_style_policy['name'],
            msg='Name of the policy is None after update')
        self.assertEquals(
            updated_cron_style_policy.cooldown, self.cron_style_policy[
                'cooldown'],
            msg='Cooldown of the policy in null after an update')
        self.assertEquals(
            updated_cron_style_policy.change, self.cron_style_policy['change'],
            msg='Change in the policy is not as expected')
        self.assertEquals(
            updated_cron_style_policy.args.cron, upd_args['cron'],
            msg='Cron style schedule policy did not update for group {0}'
            .format(self.group.id))

    def test_update_scheduler_at_style_policy_after_deletion(self):
        """
        Negative Test: Update scheduler at-style policy after policy is deleted fails
        with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        update_policy_err_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'],
            name=self.at_style_policy['name'],
            cooldown=self.at_style_policy['cooldown'],
            change=self.at_style_policy['change'],
            policy_type=self.at_style_policy['type'],
            args={'at': self.at_value})
        self.assertEquals(update_policy_err_response.status_code, 404,
                          msg='Update deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              update_policy_err_response.status_code, self.group.id,
                              self.at_style_policy['id']))

    def test_update_scheduler_cron_style_policy_after_deletion(self):
        """
        Negative Test: Update scheduler policy with cron style after policy is deleted
        fails with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        update_policy_err_response = self.autoscale_client.update_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'],
            name=self.cron_style_policy['name'],
            cooldown=self.cron_style_policy['cooldown'],
            change=self.cron_style_policy['change'],
            policy_type=self.cron_style_policy['type'],
            args={'cron': self.cron_value})
        self.assertEquals(update_policy_err_response.status_code, 404,
                          msg='Update deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              update_policy_err_response.status_code, self.group.id,
                              self.cron_style_policy['id']))

    def _update_policy(self, group_id, policy, upd_args):
        """
        Updates the policy with the given schedule value
        """
        update_policy_response = self.autoscale_client.update_policy(
            group_id=group_id,
            policy_id=policy['id'],
            name=policy['name'],
            cooldown=policy['cooldown'],
            change=policy['change'],
            policy_type=policy['type'],
            args=upd_args)
        policy_response = self.autoscale_client.get_policy_details(
            group_id,
            policy['id'])
        updated_policy = policy_response.entity
        self.assertEquals(update_policy_response.status_code, 204,
                          msg='Update scaling policy failed with {0}'
                          .format(update_policy_response.status_code))
        self.assertTrue(update_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(update_policy_response.headers)
        return updated_policy
