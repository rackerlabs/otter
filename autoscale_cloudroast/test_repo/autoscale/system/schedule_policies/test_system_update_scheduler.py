"""
Test update scheduler policies are executed as expected before and after
updates
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from time import sleep
from cafe.drivers.unittest.decorators import tags


class UpdateSchedulerTests(AutoscaleFixture):

    """
    Verify updated scheduler policy executes
    """

    def setUp(self):
        """
        Create a scaling group with minentities=0 and cooldown=0
        """
        super(UpdateSchedulerTests, self).setUp()
        create_group_response = self.autoscale_behaviors.create_scaling_group_given(
            lc_name="update_scheduler",
            gc_cooldown=0)
        self.group = create_group_response.entity
        self.resources.add(self.group, self.empty_scaling_group)

    @tags(speed='slow')
    def test_system_update_at_style_scheduler_to_execute_now(self):
        """
        Create an at style scheduler policy to execute next week,
        update the policy to execute in the next few seconds and
        verify the servers are as expected.
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(604800))
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)
        upd_args = {'at': self.autoscale_behaviors.get_time_in_utc(10)}
        self._update_policy(self.group.id, at_style_policy, upd_args)
        sleep(10 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                at_style_policy['change'])

    @tags(speed='slow')
    def test_system_update_at_style_scheduler_to_execute_in_the_future(self):
        """
        Create an at style scheduler policy to execute in the next few seconds,
        update the policy to execute after 10 secs and verify the scheduler policy
        triggers server creation as expected.
        """
        at_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            schedule_at=self.autoscale_behaviors.get_time_in_utc(5),
            sp_cooldown=0)
        sleep(5 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                at_style_policy['change'])
        upd_args = {'at': self.autoscale_behaviors.get_time_in_utc(10)}
        self._update_policy(self.group.id, at_style_policy, upd_args)
        sleep(10 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                (at_style_policy['change'] * 2))

    @tags(speed='slow')
    def test_system_update_cron_style_scheduler_to_execute_now(self):
        """
        Create an cron style scheduler policy to execute on a future day,
        update the policy to execute in the next minute and
        verify the server count on the group is as expected.
        """
        upd_args = {'cron': '* * * * *'}
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            schedule_cron='0 23 1 12 *')
        sleep(self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities)
        self._update_policy(self.group.id, cron_style_policy, upd_args)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                cron_style_policy['change'])

    @tags(speed='slow')
    def test_system_update_cron_style_scheduler_to_execute_in_the_future(self):
        """
        Create an cron style scheduler policy to execute the next minute,
        update the policy to execute every 2 minutes and
        verify the server count on the group is as expected when the policy is updated,
        wait one minute after the policy update and verify the older policy (every minute)
        is not executed.
        """
        upd_args = {'cron': '*/2 * * * *'}
        cron_style_policy = self.autoscale_behaviors.create_schedule_policy_given(
            group_id=self.group.id,
            schedule_cron='* * * * *',
            sp_cooldown=0)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                cron_style_policy['change'])
        self._update_policy(self.group.id, cron_style_policy, upd_args)
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                (cron_style_policy['change'] * 2))
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                (cron_style_policy['change'] * 2))
        sleep(60 + self.scheduler_interval)
        self.verify_group_state(self.group.id, self.group.groupConfiguration.minEntities +
                                (cron_style_policy['change'] * 3))

    def _update_policy(self, group_id, policy, upd_args, cooldown=None, change_value=None):
        """
        Updates the policy with the given values
        """
        change_value = policy['change'] if not change_value else change_value
        cooldown = policy['cooldown'] if not cooldown else cooldown
        update_policy_response = self.autoscale_client.update_policy(
            group_id=group_id,
            policy_id=policy['id'],
            name='updated_scheduler_policy',
            cooldown=cooldown,
            change=change_value,
            policy_type=policy['type'],
            args=upd_args)
        self.assertEqual(update_policy_response.status_code, 204, msg='update scheduler'
                         ' policy resulted in {0}'.format(update_policy_response.status_code))
        updated_policy = (self.autoscale_client.get_policy_details(group_id,
                                                                   policy['id'])).entity
        return updated_policy
