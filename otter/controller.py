"""
The Otter Controller:  Because otherwise your otters will make a mess of your
house.  Don't believe me?  There are videos on pet otters on youtube!

The Otter Controller manages a set of non-user visible state information for
each group, holds a lock on that state information, receives events from the
model object (group config change, scaling policy execution), and receives
events from the supervisor (job completed)

TODO:
 * Lock yak shaving
 * Eviction policy

Storage model for state information:
 * active list
    * Instance links
    * Created time
 * pending list
    * Job ID
 * last touched information for group
 * last touched information for policy
"""
from datetime import datetime
from decimal import Decimal, ROUND_UP
from functools import partial
import iso8601
import json

from twisted.internet import defer

from otter.supervisor import get_supervisor
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.util.deferredutils import unwrap_first_error
from otter.util.timestamp import from_timestamp


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
    raise NotImplementedError('Pause is not yet implemented')


def resume_scaling_group(log, transaction_id, scaling_group):
    """
    Resumes the scaling group, causing all scaling policy executions to be
    evaluated as normal again.  This is an idempotent change, if it's already
    paused, this does not raise an error.

    :raises: :class:`NoSuchScalingGroup` if the scaling group does not exist.

    :return: None
    """
    raise NotImplementedError('Resume is not yet implemented')


def obey_config_change(log, transaction_id, config, scaling_group, state):
    """
    Given the config change, do servers need to be started or deleted

    Ignore all cooldowns.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param dict config: the scaling group config
    :param scaling_group: an IScalingGroup provider
    :param state: a :class:`otter.models.interface.GroupState` representing the
        state

    :return: a ``Deferred`` that fires with the updated (or not)
        :class:`otter.models.interface.GroupState` if successful
    """
    bound_log = log.bind(scaling_group_id=scaling_group.uuid)

    # XXX:  this is a hack to create an internal zero-change policy so
    # calculate delta will work
    delta = calculate_delta(bound_log, state, config, {'change': 0})

    if delta == 0:
        return defer.succeed(state)
    elif delta > 0:
        deferred = scaling_group.view_launch_config()
        deferred.addCallback(partial(execute_launch_config, bound_log,
                                     transaction_id, state,
                                     scaling_group=scaling_group, delta=delta))
        deferred.addCallback(lambda _: state)
        return deferred
    else:
        # delta < 0 (scale down)
        deferred = exec_scale_down(bound_log, transaction_id, state, scaling_group, -delta)
        deferred.addCallback(lambda _: state)
        return deferred


def maybe_execute_scaling_policy(
        log,
        transaction_id,
        scaling_group,
        state,
        policy_id):
    """
    Checks whether and how much a scaling policy can be executed.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param scaling_group: an IScalingGroup provider
    :param state: a :class:`otter.models.interface.GroupState` representing the
        state
    :param policy_id: the policy id to execute

    :return: a ``Deferred`` that fires with the updated
        :class:`otter.models.interface.GroupState` if successful

    :raises: :class:`NoSuchScalingGroupError` if this scaling group does not exist
    :raises: :class:`NoSuchPolicyError` if the policy id does not exist
    :raises: :class:`CannotExecutePolicyException` if the policy cannot be executed

    :raises: Some exception about why you don't want to execute the policy. This
        Exception should also have an audit log id
    """
    bound_log = log.bind(scaling_group_id=scaling_group.uuid, policy_id=policy_id)
    bound_log.msg("beginning to execute scaling policy")

    # make sure that the policy (and the group) exists before doing anything else
    deferred = scaling_group.get_policy(policy_id)

    def _do_get_configs(policy):
        deferred = defer.gatherResults([
            scaling_group.view_config(),
            scaling_group.view_launch_config()
        ])
        return deferred.addCallback(lambda results: results + [policy])

    deferred.addCallbacks(_do_get_configs, unwrap_first_error)

    def _do_maybe_execute(config_launch_policy):
        """
        state_config_policy should be returned by ``check_cooldowns``
        """
        config, launch, policy = config_launch_policy
        error_msg = "Cooldowns not met."

        def mark_executed(_):
            state.mark_executed(policy_id)
            return state  # propagate the fully updated state back

        if check_cooldowns(bound_log, state, config, policy, policy_id):
            delta = calculate_delta(bound_log, state, config, policy)
            execute_bound_log = bound_log.bind(server_delta=delta)
            if delta == 0:
                execute_bound_log.msg("cooldowns checked, no change in servers")
                error_msg = "Policy execution would violate min/max constraints."
                raise CannotExecutePolicyError(scaling_group.tenant_id,
                                               scaling_group.uuid, policy_id,
                                               error_msg)
            elif delta > 0:
                execute_bound_log.msg("cooldowns checked, executing launch configs")
                d = execute_launch_config(execute_bound_log, transaction_id, state,
                                          launch, scaling_group, delta)
            else:
                # delta < 0 (scale down event)
                execute_bound_log.msg("cooldowns checked, Scaling down")
                d = exec_scale_down(execute_bound_log, transaction_id, state,
                                    scaling_group, -delta)
            return d.addCallback(mark_executed)

        raise CannotExecutePolicyError(scaling_group.tenant_id,
                                       scaling_group.uuid, policy_id,
                                       error_msg)

    return deferred.addCallback(_do_maybe_execute)


def check_cooldowns(log, state, config, policy, policy_id):
    """
    Check the global cooldowns (when was the last time any policy was executed?)
    and the policy specific cooldown (when was the last time THIS policy was
    executed?)

    :param log: A twiggy bound log for logging
    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary
    :param str policy_id: the policy id that matches ``policy``

    :return: C{int}
    """
    this_now = datetime.now(iso8601.iso8601.UTC)

    timestamp_and_cooldowns = [
        (state.policy_touched.get(policy_id), policy['cooldown'], 'policy'),
        (state.group_touched, config['cooldown'], 'group'),
    ]

    for last_time, cooldown, cooldown_type in timestamp_and_cooldowns:
        if last_time is not None:
            delta = this_now - from_timestamp(last_time)
            if delta.total_seconds() < cooldown:
                log.bind(time_since_last_touched=delta.total_seconds(),
                         cooldown_type=cooldown_type,
                         cooldown_seconds=cooldown).msg("cooldown not reached")
                return False

    return True


def calculate_delta(log, state, config, policy):
    """
    Calculate the desired change in the number of servers, keeping in mind the
    minimum and maximum constraints.

    :param log: A twiggy bound log for logging
    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: C{int} representing the desired change - can be 0
    """
    current = len(state.active) + len(state.pending)
    if "change" in policy:
        desired = current + policy['change']
    elif "changePercent" in policy:
        percentage = policy["changePercent"]
        change = int((current * (Decimal(percentage) / 100)).to_integral_value(ROUND_UP))
        desired = current + change
    elif "desiredCapacity" in policy:
        desired = policy["desiredCapacity"]
    else:
        raise AttributeError(
            "Policy doesn't have attributes 'change', 'changePercent', or "
            "'desiredCapacity: {0}".format(json.dumps(policy)))

    # constrain the desired
    max_entities = config['maxEntities']
    if max_entities is None:
        max_entities = MAX_ENTITIES
    constrained = max(min(desired, max_entities), config['minEntities'])
    delta = constrained - current

    log.msg("calculating delta",
            unconstrained_desired_capacity=desired,
            constrained_desired_capacity=constrained,
            max_entities=max_entities, min_entities=config['minEntities'],
            server_delta=delta, current_active=len(state.active),
            current_pending=len(state.pending))
    return delta


def find_pending_jobs_to_cancel(log, state, delta):
    """
    Identify some pending jobs to cancel (usually for a scale down event)
    """
    if delta >= len(state.pending):  # don't bother sorting - return everything
        return state.pending.keys()

    sorted_jobs = sorted(state.pending.items(), key=lambda (_id, s): from_timestamp(s['created']),
                         reverse=True)
    return [job_id for job_id, _job_info in sorted_jobs[:delta]]


def find_servers_to_evict(log, state, delta):
    """
    Find the servers most appropriate to evict from the scaling group

    Returns list of server ``dict``
    """
    if delta >= len(state.active):  # don't bother sorting - return everything
        return state.active.values()

    # return delta number of oldest server
    sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
    return sorted_servers[:delta]


def delete_active_servers(log, transaction_id, scaling_group,
                          delta, state):
    """
    Start deleting active servers

    Returns a list of Deferreds corresponding to deletion of a server. Each Deferred
    in the list gets fired when that server is deleted
    """

    # find servers to evict
    servers_to_evict = find_servers_to_evict(log, state, delta)

    # remove all the active servers to be deleted
    for server in servers_to_evict:
        state.remove_active(server['id'])

    # then start deleting those servers
    return [get_supervisor().execute_delete_server(log, transaction_id,
                                                   scaling_group, server_info)
            for server_info in servers_to_evict]


def exec_scale_down(log, transaction_id, state, scaling_group, delta):
    """
    Execute a scale down policy
    """

    # cancel pending jobs by removing them from the state. The servers will get
    # deleted when they are finished building and their id is not found in pending
    jobs_to_cancel = find_pending_jobs_to_cancel(log, state, delta)
    for job_id in jobs_to_cancel:
        state.remove_job(job_id)

    # delete active servers if pending jobs are not enough
    remaining = delta - len(jobs_to_cancel)
    if remaining > 0:
        delete_active_servers(log, transaction_id,
                              scaling_group, remaining, state)

    return defer.succeed(None)


def execute_launch_config(log, transaction_id, state, launch, scaling_group, delta):
    """
    Execute a launch config some number of times.

    :return: Deferred
    """

    def _handle_completion(completion_deferred, job_id):
        """
        Marks a job as completed by removing it from pending.
        If successful, adds the server info to the active servers, log, and save
        If unsuccessful, TBD other stuff, log, and save.
        """
        job_log = log.bind(job_id=job_id)

        # next_round_state is a new state blob passed to these functions by
        # modify_state.  By the time these are called, state may have changed.
        def _on_success(group, next_round_state, result):
            if job_id not in next_round_state.pending:
                # server was slated to be deleted when it completed building.
                # So, deleting it now
                job_log.msg('Job removed. Deleting server')
                get_supervisor().execute_delete_server(log, transaction_id,
                                                       scaling_group, result)
            else:
                next_round_state.remove_job(job_id)
                next_round_state.add_active(result['id'], result)
                job_log.bind(server_id=result['id']).msg(
                    "Job completed, resulting in an active server.")
            return next_round_state

        def _on_failure(group, next_round_state, f):
            next_round_state.remove_job(job_id)
            job_log.err(f)
            return next_round_state

        completion_deferred.addCallbacks(
            partial(scaling_group.modify_state, _on_success),
            partial(scaling_group.modify_state, _on_failure))

        completion_deferred.addErrback(job_log.err)

    def _update_state(pending_results):
        """
        :param pending_results: ``list`` of tuples of
        ``(job_id, {'created': <job creation time>, 'jobType': [create/delete]})``
        """
        log.msg('updating state')

        for job_id, completion_deferred in pending_results:
            state.add_job(job_id)
            _handle_completion(completion_deferred, job_id)

    if delta > 0:
        log.msg("Launching some servers.")
        deferreds = [
            get_supervisor().execute_config(log, transaction_id,
                                            scaling_group, launch)
            for i in range(delta)
        ]

    pendings_deferred = defer.gatherResults(deferreds, consumeErrors=True)
    pendings_deferred.addCallback(_update_state)
    pendings_deferred.addErrback(unwrap_first_error)
    return pendings_deferred
