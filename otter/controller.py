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
import json
from datetime import datetime
from decimal import Decimal, ROUND_UP
from functools import partial

import iso8601

from twisted.internet import defer

from otter.convergence.composition import tenant_is_enabled
from otter.convergence.service import get_convergence_starter
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.log import audit
from otter.models.interface import ScalingGroupStatus
from otter.supervisor import exec_scale_down, execute_launch_config
from otter.util.config import config_value
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


def _do_convergence_audit_log(_, log, delta, state):
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
                  policy_id=None, webhook_id=None,
                  **state.get_capacity())
    return state


def obey_config_change(log, transaction_id, config, scaling_group, state,
                       launch_config):
    """
    Given the config change, do servers need to be started or deleted

    Ignore all cooldowns.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param dict config: the scaling group config
    :param dict launch_config: the scaling group launch config
    :param scaling_group: an IScalingGroup provider
    :param state: a :class:`otter.models.interface.GroupState` representing the
        state

    :return: a ``Deferred`` that fires with the updated (or not)
        :class:`otter.models.interface.GroupState` if successful
    """
    log = log.bind(scaling_group_id=scaling_group.uuid)

    # XXX: {'change': 0} is a hack to create an internal zero-change policy so
    # calculate delta will work
    d = converge(log, transaction_id, config, scaling_group, state,
                 launch_config, {'change': 0})
    if d is None:
        return defer.succeed(state)
    return d


def force_delete_group(log, trans_id, group):
    """
    Delete group even if it has resources by also deleting resources

    :param log: Bound logger
    :param str trans_id: Transaction ID of request doing this
    :param otter.models.interface.IScalingGroup scaling_group: the scaling
        group object

    :return: Deferred that fires with None
    """
    if tenant_is_enabled(group.tenant_id, config_value):
        # For convergence tenants update group status and trigger convergence
        # TODO: What about status consistency? Will this work if another
        # process is trying to update status to ERROR at same time?
        d = group.update_status(ScalingGroupStatus.DELETING)
        cs = get_convergence_starter()
        d.addCallback(
            lambda _: cs.start_convergence(log, group.tenant_id, group.uuid))
        return d
    else:
        d = empty_group(log, trans_id, group)
        return d.addCallback(lambda _: group.delete_group())


def empty_group(log, trans_id, group):
    """
    Empty a scaling group by deleting all its resources (Servers/CLB)

    :param log: Bound logger
    :param str trans_id: Transaction ID of request doing this
    :param otter.models.interface.IScalingGroup scaling_group: the scaling
        group object

    :return: Deferred that fires with None
    """
    d = group.view_manifest(with_policies=False)

    def update_config(group_info):
        group_info['groupConfiguration']['minEntities'] = 0
        group_info['groupConfiguration']['maxEntities'] = 0
        du = group.update_config(group_info['groupConfiguration'])
        return du.addCallback(lambda _: group_info)

    d.addCallback(update_config)

    def modify_state(group_info):
        d = group.modify_state(
            partial(
                obey_config_change,
                log,
                trans_id,
                group_info['groupConfiguration'],
                launch_config=group_info['launchConfiguration']))
        return d

    d.addCallback(modify_state)
    return d


def converge(log, transaction_id, config, scaling_group, state, launch_config,
             policy, config_value=config_value):
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
    :param otter.models.interface.GroupState state: the group state
    :param dict launch_config: the scaling group launch config
    :param dict policy: the policy configuration dictionary

    :return: a ``Deferred`` that fires with the updated
        :class:`otter.models.interface.GroupState` if successful. If no changes
        are to be made to the group, None will synchronously be returned.
    """
    if tenant_is_enabled(scaling_group.tenant_id, config_value):
        # Note that convergence must be run whether or not delta is 0, because
        # delta will be zero when a group is initially created with a non-zero
        # min-entities (desired=min entities, so there is technically no
        # change).

        # For non-convergence tenants, the value used for desired-capacity is
        # the sum of active+pending, which is 0, so the delta ends up being
        # the min entities due to constraint calculation.

        apply_delta(log, state.desired, state, config, policy)
        d = get_convergence_starter().start_convergence(
            log, scaling_group.tenant_id, scaling_group.uuid)

        # We honor start_convergence's deferred here so that we can communicate
        # back a strong acknowledgement that a group has been marked dirty for
        # convergence.
        return d.addCallback(lambda _: state)

    delta = calculate_delta(log, state, config, policy)
    execute_log = log.bind(server_delta=delta)

    if delta == 0:
        execute_log.msg("no change in servers")
        return None
    elif delta > 0:
        execute_log.msg("executing launch configs")
        deferred = execute_launch_config(
            execute_log, transaction_id, state, launch_config,
            scaling_group, delta)
    else:
        # delta < 0 (scale down)
        execute_log.msg("scaling down")
        deferred = exec_scale_down(execute_log, transaction_id, state,
                                   scaling_group, -delta)

    deferred.addCallback(_do_convergence_audit_log, log, delta, state)
    return deferred


def maybe_execute_scaling_policy(
        log,
        transaction_id,
        scaling_group,
        state,
        policy_id, version=None):
    """
    Checks whether and how much a scaling policy can be executed.

    :param log: A twiggy bound log for logging
    :param str transaction_id: the transaction id
    :param scaling_group: an IScalingGroup provider
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
    bound_log = log.bind(scaling_group_id=scaling_group.uuid, policy_id=policy_id)
    bound_log.msg("beginning to execute scaling policy")

    # make sure that the policy (and the group) exists before doing anything else
    deferred = scaling_group.get_policy(policy_id, version)

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
            d = converge(bound_log, transaction_id, config, scaling_group,
                         state, launch, policy)
            if d is None:
                error_msg = "No change in servers"
                raise CannotExecutePolicyError(scaling_group.tenant_id,
                                               scaling_group.uuid, policy_id,
                                               error_msg)
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


def apply_delta(log, current, state, config, policy):
    """
    Calculate a new desired number of servers based on a policy and current
    number of servers, assign that new desired number to ``state.desired``, and
    return the difference.

    :param log: A bound log for logging
    :param current: The current number of servers in a scaling group.
    :param GroupState state: the group state
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: ``int`` representing the desired change - can be 0
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
    state.desired = max(min(desired, max_entities), config['minEntities'])
    delta = state.desired - current

    log.msg(("calculating delta "
             "{current_active} + {current_pending} -> {constrained_desired_capacity}"),
            unconstrained_desired_capacity=desired,
            constrained_desired_capacity=state.desired,
            max_entities=max_entities, min_entities=config['minEntities'],
            server_delta=delta, current_active=len(state.active),
            current_pending=len(state.pending))
    return delta


def calculate_delta(log, state, config, policy):
    """
    Apply a delta based on the ``active`` and ``pending`` server data stored
    away on ``state``.

    :param log: A bound log for logging
    :param dict state: the group state
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: C{int} representing the desired change - can be 0
    """
    current = len(state.active) + len(state.pending)
    return apply_delta(log, current, state, config, policy)
