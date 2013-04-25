"""
Tests for :mod:`otter.controller`
"""
from datetime import timedelta, datetime

import mock

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from otter import controller
from otter.models.interface import IScalingGroup, NoSuchPolicyError
from otter.util.timestamp import MIN
from otter.test.utils import DeferredTestMixin, iMock, patch
from otter.models.interface import IScalingGroupState


class CalculateDeltaTestCase(TestCase):
    """
    Tests for :func:`otter.controller.calculate_delta`
    """

    def setUp(self):
        """
        Set the max and add a mock log
        """
        patcher = mock.patch.object(controller, 'MAX_ENTITIES', new=10)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_log = mock.Mock()

    def test_positive_change_within_min_max(self):
        """
        If the policy is a scale up by a fixed number,
        and a min and max are given,
        and the desired number of servers fall between the min and the max,
        then ``calculate_delta`` returns a delta that is just the policy change.
        """
        fake_policy = {'change': 5}
        fake_config = {'minEntities': 0, 'maxEntities': 300}
        fake_state = {'active': dict.fromkeys(range(5)), 'pending': {}}

        self.assertEqual(5, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_positive_change_will_hit_max(self):
        """
        If the policy is a scale up by a fixed number,
        and a min and max are given,
        and the desired number is above the max,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'change': 5}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(2, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_positive_change_but_at_max(self):
        """
        If the policy is a scale up by a fixed number,
        and a min and max are given,
        and the current active + pending is at the max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'change': 5}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_positive_change_but_at_default_max(self):
        """
        If the policy is a scale up by a fixed number,
        and a min and no max,
        and the current active + pending is at the default max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'change': 5}
        fake_config = {'minEntities': 0, 'maxEntities': None}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_negative_change_within_min_max(self):
        """
        If the policy is a scale down by a fixed number,
        and a min and max are given,
        and the desired number of servers fall between the min and the max,
        then ``calculate_delta`` returns a delta that is just the policy change.
        """
        fake_policy = {'change': -5}
        fake_config = {'minEntities': 0, 'maxEntities': 30}
        fake_state = {'active': dict.fromkeys(range(10)), 'pending': {}}

        self.assertEqual(-5, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_negative_change_will_hit_min(self):
        """
        If the policy is a scale down by a fixed number,
        and a min and max are given,
        and the desired number is below the min,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'change': -5}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(-3, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_negative_change_but_at_min(self):
        """
        If the policy is a scale down by a fixed number,
        and a min and max are given,
        and the current active + pending is at the min already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'change': -5}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': {}, 'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_positive_change_within_min_max(self):
        """
        If the policy is a scale up by x% and a min and max are given,
        and the desired number of servers fall between the min and the max,
        then ``calculate_delta`` returns a delta that is just the policy change.
        """
        fake_policy = {'changePercent': 20}
        fake_config = {'minEntities': 0, 'maxEntities': 300}
        fake_state = {'active': dict.fromkeys(range(5)), 'pending': {}}

        self.assertEqual(1, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_positive_change_will_hit_max(self):
        """
        If the policy is a scale up by x% and a min and max are given,
        and the desired number is above the max,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'changePercent': 75}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(2, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_positive_change_but_at_max(self):
        """
        If the policy is a scale up by x% and a min and max are given,
        and the current active + pending is at the max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'changePercent': 50}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_positive_change_but_at_default_max(self):
        """
        If the policy is a scale up by x% and a min and no max,
        and the current active + pending is at the default max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'changePercent': 50}
        fake_config = {'minEntities': 0, 'maxEntities': None}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_negative_change_within_min_max(self):
        """
        If the policy is a scale down by x% and a min and max are given,
        and the desired number of servers fall between the min and the max,
        then ``calculate_delta`` returns a delta that is just the policy change.
        """
        fake_policy = {'changePercent': -50}
        fake_config = {'minEntities': 0, 'maxEntities': 30}
        fake_state = {'active': dict.fromkeys(range(10)), 'pending': {}}

        self.assertEqual(-5, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_percent_negative_change_will_hit_min(self):
        """
        If the policy is a scale down by x% and a min and max are given,
        and the desired number is below the min,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'changePercent': -80}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(-3, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_percent_negative_change_but_at_min(self):
        """
        If the policy is a scale down by x% and a min and max are given,
        and the current active + pending is at the min already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'changePercent': -50}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': {}, 'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_percent_rounding(self):
        """
        When 'changePercent' is x%, ``calculate_delta`` rounds up to an integer
        away from zero.
        """
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': {}, 'pending': dict.fromkeys(range(5))}

        test_cases = [
            (50, 3), (5, 1), (75, 4),
            (-50, -3), (-5, -1), (-75, -4)]

        for change_percent, expected_delta in test_cases:
            fake_policy = {'changePercent': change_percent}
            self.assertEqual(expected_delta,
                             controller.calculate_delta(self.mock_log,
                                                        fake_state, fake_config, fake_policy))

    def test_desired_positive_change_within_min_max(self):
        """
        If the policy is based on desiredCapacity and a min and max are given,
        and the desired number of servers fall between the min and the max,
        then ``calculate_delta`` returns a delta that is just the policy change.
        """
        fake_policy = {'desiredCapacity': 25}
        fake_config = {'minEntities': 0, 'maxEntities': 300}
        fake_state = {'active': dict.fromkeys(range(5)), 'pending': {}}

        self.assertEqual(20, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_desired_positive_change_will_hit_max(self):
        """
        If the policy is based on desiredCapacity and a min and max are given,
        and the desired number is above the max,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'desiredCapacity': 15}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(2, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_desired_positive_change_but_at_max(self):
        """
        If the policy is based on desiredCapacity  and a min and max are given,
        and the current active + pending is at the max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'desiredCapacity': 15}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_desired_positive_change_but_at_default_max(self):
        """
        If the policy is based on desiredCapacity and a min and no max,
        and the current active + pending is at the default max already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'desiredCapacity': 15}
        fake_config = {'minEntities': 0, 'maxEntities': None}
        fake_state = {'active': dict.fromkeys(range(5)),
                      'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_desired_will_hit_min(self):
        """
        If the policy is based on desiredCapacity and a min and max are given,
        and the desired number is below the min,
        then ``calculate_delta`` returns a truncated delta.
        """
        fake_policy = {'desiredCapacity': 3}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': dict.fromkeys(range(4)),
                      'pending': dict.fromkeys(range(4))}

        self.assertEqual(-3, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                        fake_policy))

    def test_desired_at_min(self):
        """
        If the policy is based on desiredCapacity and a min and max are given,
        and the current active + pending is at the min already,
        then ``calculate_delta`` returns 0.
        """
        fake_policy = {'desiredCapacity': 3}
        fake_config = {'minEntities': 5, 'maxEntities': 10}
        fake_state = {'active': {}, 'pending': dict.fromkeys(range(5))}

        self.assertEqual(0, controller.calculate_delta(self.mock_log, fake_state, fake_config,
                                                       fake_policy))

    def test_no_change_or_percent_or_desired_fails(self):
        """
        If 'change' or 'changePercent' or 'desiredCapacity' is not there in scaling policy,
        then ``calculate_delta`` doesn't know how to handle the policy
        """
        fake_policy = {'changeNone': 5}
        fake_config = {'minEntities': 0, 'maxEntities': 10}
        fake_state = {'active': {}, 'pending': {}}

        self.assertRaises(NotImplementedError,
                          controller.calculate_delta,
                          self.mock_log, fake_state, fake_config, fake_policy)


class CheckCooldownsTestCase(TestCase):
    """
    Tests for :func:`otter.controller.check_cooldowns`
    """

    def setUp(self):
        """
        Generate a mock log
        """
        self.mock_log = mock.MagicMock()

    def mock_now(self, seconds_after_min):
        """
        Set :func:`otter.util.timestamp.now` to return a timestamp that is
        so many seconds after `datetime.min`.  Tests using this should set
        the last touched time to be MIN.
        """
        def _fake_now(timezone):
            fake_datetime = datetime.min + timedelta(seconds=seconds_after_min)
            return fake_datetime.replace(tzinfo=timezone)

        self.datetime = patch(self, 'otter.controller.datetime', spec=['now'])
        self.datetime.now.side_effect = _fake_now

    def test_check_cooldowns_global_cooldown_and_policy_cooldown_pass(self):
        """
        If both the global cooldown and policy cooldown are sufficiently long
        ago, ``check_cooldowns`` returns True.
        """
        self.mock_now(30)
        fake_config = fake_policy = {'cooldown': 0}
        fake_state = {'groupTouched': MIN, 'policyTouched': {'pol': MIN}}
        self.assertTrue(controller.check_cooldowns(self.mock_log, fake_state, fake_config,
                                                   fake_policy, 'pol'))

    def test_check_cooldowns_global_cooldown_passes_policy_never_touched(self):
        """
        If the global cooldown was sufficiently long ago and the policy has
        never been executed (hence there is no touched time for the policy),
        ``check_cooldowns`` returns True.
        """
        self.mock_now(30)
        fake_config = {'cooldown': 0}
        fake_policy = {'cooldown': 10000000}
        fake_state = {'groupTouched': MIN, 'policyTouched': {}}
        self.assertTrue(controller.check_cooldowns(self.mock_log, fake_state, fake_config,
                                                   fake_policy, 'pol'))

    def test_check_cooldowns_no_policy_ever_executed(self):
        """
        If no policy has ever been executed (hence there is no global touch
        time), ``check_cooldowns`` returns True.
        """
        self.mock_now(30)
        fake_config = {'cooldown': 1000000000}
        fake_policy = {'cooldown': 10000000}
        fake_state = {'groupTouched': None, 'policyTouched': {}}
        self.assertTrue(controller.check_cooldowns(self.mock_log, fake_state, fake_config,
                                                   fake_policy, 'pol'))

    def test_check_cooldowns_global_cooldown_fails(self):
        """
        If the last time a (any) policy was executed is too recent,
        ``check_cooldowns`` returns False.
        """
        self.mock_now(1)
        fake_config = {'cooldown': 30}
        fake_policy = {'cooldown': 1000000000}
        fake_state = {'groupTouched': MIN, 'policyTouched': {}}
        self.assertFalse(controller.check_cooldowns(self.mock_log, fake_state, fake_config,
                                                    fake_policy, 'pol'))

    def test_check_cooldowns_policy_cooldown_fails(self):
        """
        If the last time THIS policy was executed is too recent,
        ``check_cooldowns`` returns False.
        """
        self.mock_now(1)
        fake_config = {'cooldown': 1000000000}
        fake_policy = {'cooldown': 30}
        fake_state = {'groupTouched': MIN, 'policyTouched': {'pol': MIN}}
        self.assertFalse(controller.check_cooldowns(self.mock_log, fake_state, fake_config,
                                                    fake_policy, 'pol'))


class MaybeExecuteScalingPolicyTestCase(DeferredTestMixin, TestCase):
    """
    Tests for :func:`otter.controller.maybe_execute_scaling_policy`
    """

    def setUp(self):
        """
        Mock relevant controller methods and also the supervisor.
        Also build a mock model that can be used for testing.
        """
        self.mocks = {}
        things_and_return_vals = {
            'check_cooldowns': True,
            'calculate_delta': 1,
            'execute_launch_config': defer.succeed(None)
        }

        for thing, return_val in things_and_return_vals.iteritems():
            self.mocks[thing] = patch(self, 'otter.controller.{0}'.format(thing),
                                      return_value=return_val)

        self.mock_log = mock.MagicMock()

        self.group = iMock(IScalingGroup, tenant_id='tenant', uuid='group')
        self.group.view_config.return_value = defer.succeed("config")
        self.group.get_policy.return_value = defer.succeed("policy")
        self.group.view_state.return_value = defer.succeed("state")
        self.group.view_launch_config.return_value = defer.succeed("launch")

    def test_maybe_execute_scaling_policy_no_such_policy(self):
        """
        If there is no such scaling policy, the whole thing fails and
        ``NoSuchScalingPolicy`` gets propagated up.  No other model access
        happens, and the lock is still released.
        """
        self.group.get_policy.return_value = defer.fail(
            NoSuchPolicyError('1', '1', '1'))

        d = controller.maybe_execute_scaling_policy(self.mock_log, 'transaction',
                                                    self.group, 'pol1')
        self.assert_deferred_failed(d, NoSuchPolicyError)

        self.assertEqual(len(self.group.view_config.mock_calls), 0)
        self.assertEqual(len(self.group.view_launch_config.mock_calls), 0)
        self.assertEqual(len(self.group.view_state.mock_calls), 0)

    def test_maybe_execute_scaling_policy_success(self):
        """
        If lock is acquired, all cooldowns are all fine, the delta is not zero,
        and ``execute_launch_config`` does not fail, return value is whatever
        ``execute_launch_config`` returns.
        """
        self.mocks['execute_launch_config'].return_value = defer.succeed(
            'this should be returned')

        d = controller.maybe_execute_scaling_policy(self.mock_log, 'transaction',
                                                    self.group, 'pol1')

        result = self.successResultOf(d)
        self.assertEqual(result, 'this should be returned')

        # log should have been updated
        self.mock_log.bind.assert_called_once_with(
            scaling_group=self.group.uuid, policy_id='pol1')

        self.mocks['check_cooldowns'].assert_called_once_with(
            self.mock_log.bind.return_value, "state", "config", "policy", 'pol1')
        self.mocks['calculate_delta'].assert_called_once_with(
            self.mock_log.bind.return_value, "state", "config", "policy")
        self.mocks['execute_launch_config'].assert_called_once_with(
            self.mock_log.bind.return_value.bind.return_value,
            'transaction', "state", "launch", self.group,
            self.mocks['calculate_delta'].return_value)

    def test_maybe_execute_scaling_policy_cooldown_failure(self):
        """
        If cooldowns are not fine, ``maybe_execute_scaling_policy`` raises a
        ``CannotExecutePolicyError`` exception.  Release lock still happens.
        """
        self.mocks['check_cooldowns'].return_value = False

        d = controller.maybe_execute_scaling_policy(self.mock_log, 'transaction',
                                                    self.group, 'pol1')
        f = self.assert_deferred_failed(d, controller.CannotExecutePolicyError)
        self.assertIn("Cooldowns not met", str(f.value))

        self.mocks['check_cooldowns'].assert_called_once_with(
            self.mock_log.bind.return_value, "state", "config", "policy", 'pol1')
        self.assertEqual(len(self.mocks['calculate_delta'].mock_calls), 0)
        self.assertEqual(len(self.mocks['execute_launch_config'].mock_calls), 0)

    def test_maybe_execute_scaling_policy_zero_delta(self):
        """
        If cooldowns are fine, but delta is zero,
        ``maybe_execute_scaling_policy`` raises a ``CannotExecutePolicyError``
        exception.  Release lock still happens.
        """
        self.mocks['calculate_delta'].return_value = 0

        d = controller.maybe_execute_scaling_policy(self.mock_log, 'transaction',
                                                    self.group, 'pol1')
        f = self.assert_deferred_failed(d, controller.CannotExecutePolicyError)
        self.assertIn("Policy execution would violate min/max constraints",
                      str(f.value))

        self.mocks['check_cooldowns'].assert_called_once_with(
            self.mock_log.bind.return_value, "state", "config", "policy", 'pol1')
        self.mocks['calculate_delta'].assert_called_once_with(
            self.mock_log.bind.return_value, "state", "config", "policy")
        self.assertEqual(len(self.mocks['execute_launch_config'].mock_calls), 0)


class ExecuteLaunchConfigTestCase(DeferredTestMixin, TestCase):
    """
    Tests for :func:`otter.controller.execute_launch_config`
    """

    def setUp(self):
        """
        Mock relevant controller methods, and also the supervisor.
        Also build a mock model that can be used for testing.
        """
        self.complete_job = patch(
            self, 'otter.controller._complete_pending_job', return_value=None)
        self.authenticate_tenant = patch(
            self, 'otter.controller.authenticate_tenant')

        self.execute_config_deferreds = []

        def fake_execute(*args, **kwargs):
            d = defer.Deferred()
            self.execute_config_deferreds.append(d)
            return defer.succeed((str(len(self.execute_config_deferreds)), d, {}))

        self.execute_config = patch(
            self, 'otter.controller.supervisor.execute_config',
            side_effect=fake_execute)

        self.log = mock.MagicMock()

        self.group = iMock(IScalingGroupState, tenant_id='tenant', uuid='group')
        self.group.update_jobs.return_value = defer.succeed(None)

        self.fake_state = {'active': {}, 'pending': {}}

    def test_positive_delta_execute_config_called_delta_times(self):
        """
        If delta > 0, ``execute_launch_config`` calls
        ``supervisor.execute_config`` delta times.
        """
        controller.execute_launch_config(self.log, '1', self.fake_state,
                                         'launch', self.group, 5)
        self.assertEqual(self.execute_config.mock_calls,
                         [mock.call(self.log, '1', self.authenticate_tenant,
                                    self.group, 'launch')] * 5)

    def test_positive_delta_excute_config_failures_propagated(self):
        """
        ``execute_launch_config`` fails if ``execute_config`` fails for any one
        case, and propagates the first ``execute_config`` error.
        """
        class ExecuteException(Exception):
            pass

        def fake_execute(*args, **kwargs):
            if len(self.execute_config_deferreds) > 1:
                return defer.fail(ExecuteException('no more!'))
            d = defer.Deferred()
            self.execute_config_deferreds.append(d)
            return defer.succeed((str(len(self.execute_config_deferreds)), d, {}))

        self.execute_config.side_effect = fake_execute
        d = controller.execute_launch_config(self.log, '1', self.fake_state,
                                             'launch', self.group, 3)
        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(ExecuteException))

    def test_negative_delta_not_implemented(self):
        """
        ``execute_launch_config`` raises ``NotImplementedError`` if the delta
        is not positive
        """
        self.assertRaises(
            NotImplementedError,
            controller.execute_launch_config,
            self.log, '1', self.fake_state, 'launch', self.group, -5)

    def test_assertion_error_when_adding_already_exiting_job(self):
        """
        If there is already a job in ``pending`` with the same ID,
        ``execute_launch_config`` raises an ``AssertionError``.
        """
        self.fake_state['pending']['1'] = None
        d = controller.execute_launch_config(self.log, '1', self.fake_state,
                                             'launch', self.group, 1)
        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(AssertionError))

    def test_update_jobs_called_with_new_jobs(self):
        """
        ``execute_launch_config`` calls ``update_jobs`` with a full pending jobs
        dictionary containing both old and new jobs
        """
        self.fake_state = {'active': {'1': None}, 'pending': {'old': None}}
        controller.execute_launch_config(self.log, '1', self.fake_state,
                                         'launch', self.group, 3)
        self.group.update_jobs.assert_called_once_with(
            self.fake_state, {'old': None, '1': {}, '2': {}, '3': {}}, '1')

    def test_propagates_update_jobs_return_value(self):
        """
        ``execute_launch_config`` returns whatever value ``update_jobs`` returns
        """
        self.group.update_jobs.return_value = defer.succeed('hey!')
        d = controller.execute_launch_config(self.log, '1', self.fake_state,
                                             'launch', self.group, 1)
        self.assertEqual(self.successResultOf(d), 'hey!')

    def test_propagates_update_jobs_failures(self):
        """
        ``execute_launch_config`` fails if ``update_jobs`` fails
        """
        self.group.update_jobs.return_value = defer.fail(Exception('boo!'))
        d = controller.execute_launch_config(self.log, '1', self.fake_state,
                                             'launch', self.group, 1)
        failure = self.failureResultOf(d)
        self.assertTrue(failure.check(Exception))

    def test_complete_pending_called_when_jobs_done(self):
        """
        ``execute_launch_config`` sets it up so that ``_complete_pending_job``
        gets called whenever a job finishes, whether successfully or not
        """
        controller.execute_launch_config(self.log, '1', self.fake_state,
                                         'launch', self.group, 3)

        self.execute_config_deferreds[0].callback(None)              # job id 1
        self.execute_config_deferreds[1].errback(Exception('meh'))   # job id 2
        self.execute_config_deferreds[2].callback(None)              # job id 3

        self.assertEqual(self.complete_job.mock_calls,
                         [mock.call(self.log, '1', True),
                          mock.call(self.log, '2', False),
                          mock.call(self.log, '3', True)])
