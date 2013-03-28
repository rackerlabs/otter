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

from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.supervisor import execute_one_config
from otter.util.timestamp import now, from_timestamp


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
        scaling_group,
        policy_id):
    """
    Checks whether and how much a scaling policy can be executed.

    :param scaling_group: an IScalingGroup provider
    :param policy_id: the policy id to execute

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
    if check_cooldowns('fake', 'fake', 'fake', 'fake'):
        delta = calculate_delta("fake", "fake", "fake")
        execute_launch_config(log, transaction_id, state, scaling_group, delta)
        #record_policy_trigger_time(log, scaling_group, policy, time.time())
    #else:
        #record_policy_decision_time(log, scaling_group, policy, time.time(),
        #                            'i was rejected because...')


def check_cooldowns(state, config, policy, policy_id):
    """
    Check the cooldowns -- needs further definition

    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary
    :param str policy_id: the policy id that matches ``policy``

    :return: ``True`` if the policy does not run afoul any cooldowns, ``False``
        otherwise
    """
    # hack to get a timezone aware date-time object of the same timezone as
    # gets returned by from_timestamp, because we cannot perform any math if
    # one datetime object is timezone aware and the other is not
    this_now = from_timestamp(now())

    timestamp_and_cooldowns = [
        (state['policyTouched'].get(policy_id), policy['cooldown']),
        (state['groupTouched'], config['cooldown']),
    ]

    for last_time, cooldown in timestamp_and_cooldowns:
        if last_time is not None:
            delta = this_now - from_timestamp(last_time)
            if delta.total_seconds() < cooldown:
                return False

    return True


def calculate_delta(state, config, policy):
    """
    Calculate the desired change in the number of servers, keeping in mind the
    minimum and maximum constraints.

    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: C{int} representing the desired change - can be 0
    """
    def constrain(desired):
        max_entities = config['maxEntities']
        if max_entities is None:
            max_entities = MAX_ENTITIES
        return max(min(desired, max_entities), config['minEntities'])

    if "change" in policy:
        current = len(state['active']) + len(state['pending'])
        return constrain(current + policy['change']) - current
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
