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
from datetime import datetime
import iso8601

from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.util.timestamp import from_timestamp

from twisted.internet import defer
from otter import supervisor
from otter.util.deferredutils import unwrap_first_error


class CannotExecutePolicyError(Exception):
    """
    Exception to be raised when the policy cannot be executed
    """
    def __init__(self, tenant_id, group_id, policy_id, why):
        super(CannotExecutePolicyError, self).__init__(
            "Cannot execute scaling policy {p} for group {g} for tenant {t}: {w}"
            .format(t=tenant_id, g=group_id, p=policy_id, w=why))


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

    :return: a ``Deferred`` that fires with None

    :raises: :class:`NoSuchScalingGroupError` if this scaling group does not exist
    :raises: :class:`NoSuchPolicyError` if the policy id does not exist
    :raises: :class:`CannotExecutePolicyException` if the policy cannot be executed

    :raises: Some exception about why you don't want to execute the policy. This
    Exception should also have an audit log id

    policy example:
           {
                "name": "scale up by 10",
                "change": 10,
                "cooldown": 5
            },


    """
    bound_log = log.fields(
        scaling_group=scaling_group.uuid, policy_id=policy_id)

    # make sure that the policy (and the group) exists before doing anything else
    deferred = scaling_group.get_policy(policy_id)

    def _do_get_config_and_state(policy):
        deferred = defer.gatherResults([
            scaling_group.view_state(),
            scaling_group.view_config(),
            scaling_group.view_launch_config()
        ])
        return deferred.addCallback(lambda results: results + [policy])

    deferred.addCallbacks(_do_get_config_and_state, unwrap_first_error)

    def _do_maybe_execute(state_config_launch_policy):
        """
        state_config_policy should be returned by ``check_cooldowns``
        """
        state, config, launch, policy = state_config_launch_policy
        error_msg = "Cooldowns not met."

        if check_cooldowns(state, config, policy, policy_id):
            delta = calculate_delta(state, config, policy)
            if delta != 0:
                return execute_launch_config(bound_log, transaction_id, state,
                                             launch, scaling_group, delta)
            error_msg = "Policy execution would violate min/max constraints."

        raise CannotExecutePolicyError(scaling_group.tenant_id,
                                       scaling_group.uuid, policy_id,
                                       error_msg)

    return deferred.addCallback(_do_maybe_execute)


def check_cooldowns(state, config, policy, policy_id):
    """
    Check the global cooldowns (when was the last time any policy was executed?)
    and the policy specific cooldown (when was the last time THIS policy was
    executed?)

    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary
    :param str policy_id: the policy id that matches ``policy``

    :return: C{int}
    """
    this_now = datetime.now(iso8601.iso8601.UTC)

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


def find_pending_jobs_to_cancel(log, state, delta):
    """
    Identify some jobs to cancel (usually for a scale down event)
    """
    return []


def find_server_to_evict(log, state, delta):
    """
    Find the server most appropriate to evict from the scaling group
    """
    return []


def execute_launch_config(log, transaction_id, state, launch, scaling_group, delta):
    """
    Execute a launch config some number of times.

    :return: Deferred
    """
    def _update_state(pending_results):
        """
        :param pending_results: ``list`` of tuples of
        ``(job_id, {'created': <job creation time>, 'jobType': [create/delete]})``
        """
        jobs_dict = state['pending'].copy()

        for job_id, job_info in pending_results:
            if job_id in state['pending']:
                raise Exception('what????!!! {0} already exists'.format(job_id))
            jobs_dict[job_id] = job_info

        return scaling_group.update_jobs(state, jobs_dict, transaction_id)

    if delta > 0:
        deferreds = [
            supervisor.execute_one_config(log, transaction_id,
                                          scaling_group, launch)
            for i in range(abs(delta))
        ]
    else:
        deferreds = [supervisor.cancel_job(log, transaction_id, scaling_group, job_id)
                     for job_id in find_pending_jobs_to_cancel(log, state, delta)]

        if len(deferreds) < delta:
            deferreds.extend([
                supervisor.evict_server(log, transaction_id, scaling_group, server_id)
                for server_id in find_server_to_evict(log, state, delta - len(deferreds))
            ])

    pendings_deferred = defer.gatherResults(deferreds)
    pendings_deferred.addCallback(_update_state)
    return pendings_deferred
