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
import iso8601
import json

from twisted.internet import defer

from otter.log import audit
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.util.deferredutils import unwrap_first_error
from otter.util.timestamp import from_timestamp
from otter.supervisor import execute_launch_config, exec_scale_down


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


def _do_convergence_audit_log(_, log, delta):
    """
    Logs a convergence event to the audit log
    """
    audit_log = audit(log)

    if delta < 0:
        msg = "Deleting {0}".format(-delta)
        event_type = "convergence.scale_down"
    else:
        msg = "Starting {convergence_delta} new"
        event_type = "convergence.scale_up"

    msg += " servers to satisfy desired capacity"

    audit_log.msg(msg, event_type=event_type, convergence_delta=delta,
                  # setting policy_id/webhook_id to None is a hack to prevent
                  # them from making it into the audit log
                  policy_id=None, webhook_id=None)


def obey_config_change(log, transaction_id, config, scaling_group, desired,
                       launch_config):
    """
    Given the config change, do servers need to be started or deleted

    Ignore all cooldowns.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param dict config: the scaling group config
    :param dict launch_config: the scaling group launch config
    :param scaling_group: an IScalingGroup provider
    :param int desired: current desired value

    :return: a ``Deferred`` that fires with the updated (or not) desired if successful
    """
    log = log.bind(scaling_group_id=scaling_group.uuid)

    # XXX: {'change': 0} is a hack to create an internal zero-change policy so
    # calculate delta will work
    d = converge(log, transaction_id, config, scaling_group, desired,
                 launch_config, {'change': 0})
    d.addCallback(lambda d: desired if d is None else d)
    return d


def converge(log, transaction_id, config, scaling_group, desired, launch_config,
             policy):
    """
    Apply a policy's change to a scaling group, and attempt to make the
    resulting state a reality. This does no cooldown checking.

    This is done by dispatching to the appropriate orchestration backend for
    the scaling group; currently only direct nova interaction is supported.

    :param log: A bound log for logging
    :param str transaction_id: the transaction id
    :param dict config: the scaling group config
    :param otter.models.interface.IScalingGroup scaling_group: the scaling
        group object
    :param int desired: Current desired value
    :param otter.models.interface.GroupState state: the group state
    :param dict launch_config: the scaling group launch config
    :param dict policy: the policy configuration dictionary

    :return: a ``Deferred`` that fires with the updated desired value if successful.
             Otherwise, it will be fired with None
    """
    # Get number of pending and active servers
    # TODO: Handle pagination
    d = scaling_group.get_servers_collection().list_servers(log)

    # Calculate delta
    d.addCallback(lambda servers: (len(servers),
                                   calculate_delta(log, len(servers), config, policy)))

    def _start_scaling((current, delta)):
        execute_log = log.bind(server_delta=delta)
        if delta == 0:
            execute_log.msg("no change in servers")
            return None
        elif delta > 0:
            execute_log.msg("executing launch configs")
            deferred = execute_launch_config(execute_log, transaction_id,
                                             launch_config, scaling_group, delta)
        else:
            # delta < 0 (scale down)
            execute_log.msg("scaling down")
            deferred = exec_scale_down(execute_log, transaction_id, scaling_group, -delta)
        deferred.addCallback(_do_convergence_audit_log, log, delta)
        return deferred.addCallback(lambda _: current + delta)

    # Start/stop servers
    d.addCallback(_start_scaling)
    return d


def maybe_execute_scaling_policy(
        log,
        transaction_id,
        group,
        desired,
        policy_id, version=None):
    """
    Checks whether and how much a scaling policy can be executed.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param group: an IScalingGroup provider
    :param state: a :class:`otter.models.interface.GroupState` representing the
        state
    :param policy_id: the policy id to execute
    :param version: the policy version to check before executing

    :return: a ``Deferred`` that fires with the updated
        :class:`otter.models.interface.GroupState` if successful

    :raises: :class:`NoSuchScalingGroupError` if this scaling group does not exist
    :raises: :class:`NoSuchPolicyError` if the policy id does not exist
    :raises: :class:`CannotExecutePolicyException` if the policy cannot be executed

    :raises: Some exception about why you don't want to execute the policy. This
        Exception should also have an audit log id
    """
    bound_log = log.bind(scaling_group_id=group.uuid, policy_id=policy_id)
    bound_log.msg("beginning to execute scaling policy")

    # make sure that the policy (and the group) exists before doing anything else
    deferred = group.get_policy(policy_id, version)

    def _do_get_configs(policy):
        deferred = defer.gatherResults([
            group.view_config(),
            group.view_launch_config(),
            group.last_execution_time(),
        ])
        return deferred.addCallback(lambda results: results + [policy])

    deferred.addCallbacks(_do_get_configs, unwrap_first_error)

    def _do_maybe_execute(config_launch_policy):
        """
        state_config_policy should be returned by ``check_cooldowns``
        """
        config, launch, group_exec_time, policy = config_launch_policy

        def update_exec_times(updated_desired):
            d = defer.gatherResults([group.update_execution_time(),
                                     group.update_policy_execution_time(policy_id)])
            return d.addCallback(lambda _: updated_desired)

        def check_no_change(result):
            if result is None:
                raise CannotExecutePolicyError(group.tenant_id,
                                               group.uuid, policy_id,
                                               "No change in servers")
            return result

        if check_cooldowns(bound_log, group_exec_time, config, policy, policy_id):
            # converge returns new desired
            d = converge(bound_log, transaction_id, config, group, desired, launch, policy)
            d.addCallback(check_no_change)
            d.addCallback(update_exec_times)
            return d
        else:
            raise CannotExecutePolicyError(group.tenant_id, group.uuid, policy_id,
                                           "Cooldowns not met")

    return deferred.addCallback(_do_maybe_execute)


def check_cooldowns(log, group_exec_time, config, policy, policy_id):
    """
    Check the global cooldowns (when was the last time any policy was executed?)
    and the policy specific cooldown (when was the last time THIS policy was
    executed?)

    :param log: A twiggy bound log for logging
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary
    :param str policy_id: the policy id that matches ``policy``

    :return: C{int}
    """
    # TEMP
    return True

    this_now = datetime.now(iso8601.iso8601.UTC)

    timestamp_and_cooldowns = [
        (policy['last_execution_time'], policy['cooldown'], 'policy'),
        (group_exec_time, config['cooldown'], 'group'),
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


def calculate_delta(log, current, config, policy):
    """
    Calculate the desired change in the number of servers, keeping in mind the
    minimum and maximum constraints.

    :param log: A twiggy bound log for logging
    :param int current: Current number of servers
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: C{int} representing the desired change - can be 0
    """
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
    constrained_desired = max(min(desired, max_entities), config['minEntities'])
    delta = constrained_desired - current

    log.msg(("calculating delta "
             "{current} -> {constrained_desired_capacity}"),
            unconstrained_desired_capacity=desired,
            constrained_desired_capacity=constrained_desired,
            max_entities=max_entities, min_entities=config['minEntities'],
            server_delta=delta, current=current)
    return delta
