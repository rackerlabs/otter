"""
The Otter Controller:  Because otherwise your otters will make a mess of your
house.  Don't believe me?  There are videos on pet otters on youtube!

The Otter Controller manages a set of non-user visible state information for
each group, holds a lock on that state information, receives events from the
model object (group config change, scaling policy execution), and receives
events from the supervisor (job completed)

TODO:
 * Migrate over to new storage model for state information
 * Lock yak shaving
 * cooldown
 * Eviction policy

Storage model for state information:
 * active list
  * Instance URI
  * Created time
 * pending list
  * Job ID
 * last touched information for group
 * last touched information for polciy

"""

from otter.supervisor import execute_one_config


def pause_scaling_group(log, transaction_id, scaling_group):
    """
    Pauses the scaling group, causing all scaling policy executions to be
    rejected until unpaused.  This is an idempotent change, if it's already
    paused, this does not raise an error.

    :raises: :class:`NoSuchScalingGroup` if the scaling group does not exist.

    :return: None
    """
    return None


def resume_scaling_group(log, transaction_id, scaling_group):
    """
    Resumes the scaling group, causing all scaling policy executions to be
    evaluated as normal again.  This is an idempotent change, if it's already
    paused, this does not raise an error.

    :raises: :class:`NoSuchScalingGroup` if the scaling group does not exist.

    :return: None
    """
    return None


def obey_config_change(log, transaction_id, scaling_group):
    """
    Checks to make sure, after a scaling policy config change, that
    the current steady state is within the min and max.
    """
    state = scaling_group.view_state()
    # TODO: Lock group
    # TODO: finish
    print state


def complete_pending_job(log, job_id, state):
    """
    Updates the state with a pending job, mark it as completed

    State is True if we succeeded, False if we didn't

    Recursive Forkbomb pseudocode magic!  Fill in later! That's why it's magic!
    """
    return True


def maybe_execute_scaling_policy(
        log,
        transaction_id,
        tenant_id,
        scaling_group_id,
        scaling_group_config,
        launch_config,
        policy_id,
        policy):
    """
    Checks whether and how much a scaling policy can be executed.

    :param scaling_group: an IScalingGroup provider
    :param policy: the policy id to execute

    Current plan: If a user executes a policy, return whether or not it will be
    executed. If it is going to be executed, ????

    :return: a ``Deferred`` that fires with the audit log ID of this job
    :raises: Some exception about why you don't want to execute the policy. This
    Exception should also have an audit log id

    policy example:
           {
                "name": "scale up by 10",
                "change": 10,
                "cooldown": 5
            },


    """
    # TODO: Lock group
    state = scaling_group.view_state()
    if check_cooldowns(log, scaling_group, policy, "i got this data from the db"):
        (new_state, delta) = calculate_new_steady_state(log, state, policy)
        execute_launch_config(log, transaction_id, state, scaling_group, delta)
        #record_policy_trigger_time(log, scaling_group, policy, time.time())
    #else:
        #record_policy_decision_time(log, scaling_group, policy, time.time(),
        #                            'i was rejected because...')


def check_cooldowns(*args):
    """
    Check the cooldowns -- needs further definition
    """
    return True


def calculate_new_steady_state(log, state, policy):
    """
    Calculate new steady state size and delta
    """
    if "change" in policy:
        return (state['steadyState'] + policy["change"], policy["change"])
    else:
        raise NotImplementedError()


def find_server_to_evict(log, scaling_group):
    """
    Find the server most appropriate to evict from the scaling group
    """
    return None


def execute_launch_config(log, transaction_id, state, scaling_group, delta):
    """
    Execute a launch config some number of times.
    """
    launch_config = scaling_group.view_launch_config()
    # Evicting servers cherfully ignored
    for i in range(abs(delta)):
        state['pending'].append(execute_one_config(log, transaction_id,
                                scaling_group.uuid, launch_config))
