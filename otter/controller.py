"""
Spike for the controller (accounting enforcement) interface
"""

import time
from otter.supervisor import notify_group_size_change


def maybe_execute_scaling_policy(log, transaction_id, scaling_group, policy_id):
    """
    Checks whether and how much a scaling policy can be executed.

    :param scaling_group: an IScalingGroup provider
    :param policy_id: the policy id to execute

    Current plan: If a user executes a policy, return whether or not it will be
    executed.  If it is going to be executed, ????

    :return: a ``Deferred`` that fires with the audit log ID of this job
    :raises: Some exception about why you don't want to execute the policy. This
        Exception should also have an audit log id
    """
    check_cooldowns(scaling_group, policy_id, "i got this data from the db")
    scaling_group.set_steady_state(calculate_new_steady_state())
    notify_group_size_change(transaction_id, scaling_group, policy_id)
    record_policy_trigger_time(scaling_group, policy_id, time.time())


def calculate_new_steady_state(log):
    """
    :raises: Some exception about why you don't the steady state shouldn't
        change. This Exception should also have an audit log id
    """
    raise NotImplementedError()


def check_cooldowns(log, scaling_group, policy_id, policy_data):
    """
    If the most recent trigger of any policy is within <global cooldown> of
        now, False

    If this policy is still running, or it finished within <policy cooldown>,
        then False

    If it has been <policy cooldown>+ seconds since the last time the policy finished,
        and <global cooldown>+ seconds since the last time any policy has been
        triggered, then True
    """
    raise NotImplementedError()


def record_policy_trigger_time(log, scaling_group, policy_id, timestamp):
    """
    Stores the time the policy was triggered/decided to be executed
    """
    raise NotImplementedError()
