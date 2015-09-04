"""
System tests for multiple scheduler and webhook policies
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
from cafe.drivers.unittest.decorators import tags


class MultipleSchedulerWebhookPoliciesTest(AutoscaleFixture):

    """
    System tests to verify execute multiple scaling policies'
    of type webhook and scheduler scenarios
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0
        """
        super(MultipleSchedulerWebhookPoliciesTest, self).setUp()
        self.change = 1
        self.delta = 5
        self.wb_policy = dict(cooldown=self.gc_cooldown,
                              type='webhook', name='multiple_wb_policies',
                              change=self.change)
        self.cron_style_policy = dict(
            args=dict(cron='* * * * *'),
            cooldown=self.gc_cooldown, type='schedule',
            name='multi_cron_style', change=self.change)

    @property
    def at_style_policy(self):
        return dict(
            args=dict(at=self.autoscale_behaviors.get_time_in_utc(self.delta)),
            cooldown=self.gc_cooldown, type='schedule', name='multi_at_style',
            change=self.change)

    @tags(speed='quick', convergence='yes')
    def test_group_multiple_webhook_policies_with_same_attributes(self):
        """
        Creating a group with a list of multiple webhook policies,
        with the same attributes, is succcessful
        """
        self._create_multi_policy_group(2, 201, self.wb_policy)

    @tags(speed='quick', convergence='yes')
    def test_system_create_multiple_scheduler_policies_same_payload(self):
        """
        Creating a group with a list of multiple scheduler policies,
        (at style and cron style) with the same attributes, is succcessful
        """
        self._create_multi_policy_group(
            2, 201, self.at_style_policy, self.cron_style_policy)

    @tags(speed='slow', convergence='yes')
    def test_system_webhook_and_scheduler_policies_same_group(self):
        """
        Create a group with scheduler and webhook policies and verify the
        servers after their executions are as exepected
        """
        group = self._create_multi_policy_group(
            1, 201, self.wb_policy, self.at_style_policy,
            self.cron_style_policy)
        self._execute_webhook_policies_within_group(group)
        self.wait_for_expected_group_state(
            group.id, 3 * self.change,
            self.cron_wait_timeout, 2, time_scale=False)

    @tags(speed='slow', convergence='yes')
    def test_system_webhook_and_scheduler_policies_different_groups(self):
        """
        Create 2 groups each with the same type of scheduler and webhook
        policies and verify the servers after each of their executions
        """
        group1 = self._create_multi_policy_group(
            1, 201, self.wb_policy, self.at_style_policy,
            self.cron_style_policy)
        group2 = self._create_multi_policy_group(
            1, 201, self.wb_policy, self.at_style_policy,
            self.cron_style_policy)
        self._execute_webhook_policies_within_group(group1, group2)
        sleep(self.cron_wait_timeout)
        self.verify_group_state(group1.id, 3 * self.change)
        self.verify_group_state(group2.id, 3 * self.change)

    @tags(speed='quick', convergence='yes')
    def test_system_all_types_webhook_and_scheduler_policies(self):
        """
        Creating a group with scheduler and webhook policies for all types
        of changes is successful.
        """
        wb_policy_cp = self._unchanged_policy(self.wb_policy)
        wb_policy_cp['changePercent'] = 100
        wb_policy_dc = self._unchanged_policy(self.wb_policy)
        wb_policy_dc['desiredCapacity'] = 1
        at_style_policy_cp = self._unchanged_policy(self.at_style_policy)
        at_style_policy_cp['changePercent'] = 100
        at_style_policy_dc = self._unchanged_policy(self.at_style_policy)
        at_style_policy_dc['desiredCapacity'] = 1
        cron_style_policy_cp = self._unchanged_policy(self.cron_style_policy)
        cron_style_policy_cp['changePercent'] = 100
        cron_style_policy_dc = self._unchanged_policy(self.cron_style_policy)
        cron_style_policy_dc['desiredCapacity'] = 1
        self._create_multi_policy_group(
            1, 201, self.wb_policy, self.at_style_policy,
            self.cron_style_policy, wb_policy_cp, at_style_policy_cp,
            cron_style_policy_cp, wb_policy_dc, at_style_policy_dc,
            cron_style_policy_dc)

    @tags(speed='quick', convergence='yes')
    def test_system_all_types_webhook_and_scheduler_policies_negative(self):
        """
        Creating a group with scheduler and webhook policies for all types
        of changes with invalid inputs for the chnge type and at style time,
        and verify reponse code 400 is returned.
        """
        invalid_item = 0.0001
        wb_policy_cp = self._unchanged_policy(self.wb_policy)
        wb_policy_cp['changePercent'] = invalid_item
        wb_policy_dc = self._unchanged_policy(self.wb_policy)
        wb_policy_dc['desiredCapacity'] = invalid_item
        at_style_policy_cp = self._unchanged_policy(self.at_style_policy)
        at_style_policy_cp['changePercent'] = invalid_item
        at_style_policy_dc = self._unchanged_policy(self.at_style_policy)
        at_style_policy_dc['desiredCapacity'] = invalid_item
        at_style_policy_dc['args']['at'] = '2013-12-05T03:12Z'
        cron_style_policy_cp = self._unchanged_policy(self.cron_style_policy)
        cron_style_policy_cp['changePercent'] = invalid_item
        cron_style_policy_dc = self._unchanged_policy(self.cron_style_policy)
        cron_style_policy_dc['desiredCapacity'] = invalid_item
        self._create_multi_policy_group(
            1, 400, self.wb_policy, self.at_style_policy,
            self.cron_style_policy, wb_policy_cp, at_style_policy_cp,
            cron_style_policy_cp, wb_policy_dc, at_style_policy_dc,
            cron_style_policy_dc)

    @tags(speed='quick', convergence='yes')
    def test_system_webhook_and_scheduler_policies_many_different_groups(self):
        """
        Create many groups each with the same type of scheduler and webhook
        policies and verify the servers after each of their executions
        """
        self.delta = 30
        group_ids = [
            self._create_multi_policy_group(1, 201, self.at_style_policy).id
            for _ in range(4)]
        sleep(2 + self.scheduler_interval + 30)
        for group_id in group_ids:
            self.verify_group_state(group_id, self.change)
            self.verify_server_count_using_server_metadata(group_id,
                                                           self.change)

    def _unchanged_policy(self, policy_list):
        return {i: policy_list[i] for i in policy_list if i != 'change'}

    def _create_multi_policy_group(self, multi_num, expected_code, *args):
        """
        Creates a group with the given list of policies and asserts the
        group creation was successful
        """
        policy_list = []
        for each_policy in args:
            policy_list.extend([each_policy] * multi_num)
        response = self.autoscale_behaviors.create_scaling_group_given(
            lc_name='multi_scheduling',
            sp_list=policy_list,
            gc_cooldown=0)
        self.assertEquals(
            response.status_code, expected_code,
            msg=('Creating multiple scaling policies within a group failed '
                 'with response code: {0}'.format(response.status_code)))
        group = response.entity
        self.resources.add(group, self.empty_scaling_group)
        return group

    def _execute_webhook_policies_within_group(self, *args):
        """
        Executes all the scaling policies within the given group.
        Assumes scheduled policies execute within scheduled_interval.
        """
        for each_group in args:
            for each_policy in each_group.scalingPolicies:
                if not hasattr(each_policy, 'args'):
                    execute_policy = self.autoscale_client.execute_policy(
                        each_group.id, each_policy.id)
                    self.assertEquals(
                        execute_policy.status_code, 202,
                        msg=('Executing the scaling policies within a group '
                             'failed with response code: {0}'.format(
                                 execute_policy.status_code)))
