"""
Test get scheduler policies (at and cron style).
"""
from test_repo.autoscale.fixtures import ScalingGroupFixture


class UpdateSchedulerScalingPolicy(ScalingGroupFixture):

    """
    Verify get scheduler policies
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group with minentities=0
        """
        super(UpdateSchedulerScalingPolicy, cls).setUpClass()

    def setUp(self):
        """
        Create 2 scheduler policies, one at-style and another cron-style
        """
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

    def tearDown(self):
        """
        Scaling group deleted by the Autoscale fixture's teardown
        """
        pass

    def test_get_at_style_scaling_policy(self):
        """
        Verify get at style schedule policy's response code 200, headers and data
        """
        get_at_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.at_style_policy['id'])
        self.assertEquals(get_at_style_policy_response.status_code, 200,
                          msg='Get scaling policy (at style) failed with {0} for group {1}'
                          .format(get_at_style_policy_response.status_code,
                                  self.group.id))
        self.assertTrue(get_at_style_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(get_at_style_policy_response.headers)
        get_at_style_policy = get_at_style_policy_response.entity
        self.assertEquals(
            get_at_style_policy.id, self.at_style_policy['id'],
            msg='Policy Id is not as expected upon get')
        self.assertEquals(
            get_at_style_policy.links, self.at_style_policy['links'],
            msg='Links for the scaling policy is none upon the get')
        self.assertEquals(
            get_at_style_policy.name, self.at_style_policy['name'],
            msg='Name of the policy is None upon get')
        self.assertEquals(
            get_at_style_policy.cooldown, self.at_style_policy['cooldown'],
            msg='Cooldown of the policy in null upon an get')
        self.assertEquals(
            get_at_style_policy.change, self.at_style_policy['change'],
            msg='Change in the policy is not as expected')
        self.assertEquals(get_at_style_policy.args.at, self.at_value,
                          msg='At style schedule policy value not as expected'
                          ' get for group {0}'
                          .format(self.group.id))

    def test_get_cron_style_scaling_policy(self):
        """
        Verify get cron style schedule policy's response code 200, headers and data
        """
        get_cron_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.cron_style_policy['id'])
        self.assertEquals(get_cron_style_policy_response.status_code, 200,
                          msg='Get scaling policy (cron style) failed with {0} for group {1}'
                          .format(get_cron_style_policy_response.status_code,
                                  self.group.id))
        self.assertTrue(get_cron_style_policy_response.headers is not None,
                        msg='The headers are not as expected')
        self.validate_headers(get_cron_style_policy_response.headers)
        get_cron_style_policy = get_cron_style_policy_response.entity
        self.assertEquals(
            get_cron_style_policy.id, self.cron_style_policy['id'],
            msg='Policy Id is not as expected upon get')
        self.assertEquals(
            get_cron_style_policy.links, self.cron_style_policy['links'],
            msg='Links for the scaling policy is none upon the get')
        self.assertEquals(
            get_cron_style_policy.name, self.cron_style_policy['name'],
            msg='Name of the policy is None upon get')
        self.assertEquals(
            get_cron_style_policy.cooldown, self.cron_style_policy['cooldown'],
            msg='Cooldown of the policy in null upon an get')
        self.assertEquals(
            get_cron_style_policy.change, self.cron_style_policy['change'],
            msg='Change in the policy is not as expected')
        self.assertEquals(get_cron_style_policy.args.cron, self.cron_value,
                          msg='Cron style schedule policy value not as expected'
                          ' get for group {0}'
                          .format(self.group.id))

    def test_get_scheduler_cron_style_policy_after_deletion(self):
        """
        Negative Test: get scheduler policy with cron style after policy is deleted
        fails with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.cron_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        get_cron_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.cron_style_policy['id'])
        self.assertEquals(get_cron_style_policy_response.status_code, 404,
                          msg='get deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              get_cron_style_policy_response.status_code, self.group.id,
                              self.cron_style_policy['id']))

    def test_get_scheduler_at_style_policy_after_deletion(self):
        """
        Negative Test: get scheduler policy with cron style after policy is deleted
        fails with resource not found 404
        """
        del_resp = self.autoscale_client.delete_scaling_policy(
            group_id=self.group.id,
            policy_id=self.at_style_policy['id'])
        self.assertEquals(
            del_resp.status_code, 204, msg='Delete at-style policy failed')
        get_at_style_policy_response = self.autoscale_client.get_policy_details(
            self.group.id,
            self.at_style_policy['id'])
        self.assertEquals(get_at_style_policy_response.status_code, 404,
                          msg='get deleted scheduler policy succeeded with: {0},'
                          'policy/groupid: {1} / {2}'
                          .format(
                              get_at_style_policy_response.status_code, self.group.id,
                              self.at_style_policy['id']))
