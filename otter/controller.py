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

from effect import (
    Effect,
    parallel,
    parallel_all_errors)

from effect.do import do, do_return

import iso8601

from six import reraise

from toolz.dicttoolz import get_in

from twisted.internet import defer

from txeffect import perform

from otter.cloud_client import (
    NoSuchServerError,
    TenantScope,
    get_server_details,
    set_nova_metadata_item)
from otter.convergence.composition import tenant_is_enabled
from otter.convergence.model import DRAINING_METADATA, group_id_from_metadata
from otter.convergence.service import (
    delete_divergent_flag, get_convergence_starter)
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.log import audit
from otter.log.intents import with_log
from otter.models.intents import GetScalingGroupInfo, ModifyGroupStatePaused
from otter.models.interface import GroupNotEmptyError, ScalingGroupStatus
from otter.supervisor import (
    CannotDeleteServerBelowMinError,
    ServerNotFoundError,
    exec_scale_down,
    execute_launch_config)
from otter.supervisor import (
    remove_server_from_group as worker_remove_server_from_group)
from otter.util.config import config_value
from otter.util.deferredutils import unwrap_first_error
from otter.util.fp import assoc_obj
from otter.util.retry import (
    exponential_backoff_interval,
    retry_effect,
    retry_times)
from otter.util.timestamp import from_timestamp
from otter.worker_intents import EvictServerFromScalingGroup


class CannotExecutePolicyError(Exception):
    """
    Exception to be raised when the policy cannot be executed
    """
    def __init__(self, tenant_id, group_id, policy_id, why):
        super(CannotExecutePolicyError, self).__init__(
            "Cannot execute scaling policy {p} for group {g} for tenant {t}: {w}"
            .format(t=tenant_id, g=group_id, p=policy_id, w=why))


class GroupPausedError(Exception):
    """
    Exception to be raised when an operation cannot be performed because
    group is paused
    """
    def __init__(self, tenant_id, group_id, operation, extra=None):
        fmt = "Cannot {o} for group {g} for tenant {t} because group is paused"
        if extra is not None:
            fmt = "{}. {}".format(fmt, extra)
        super(GroupPausedError, self).__init__(
            fmt.format(t=tenant_id, g=group_id, o=operation))


def conv_pause_group_eff(group, transaction_id):
    """
    Pause scaling group of convergence enabled tenant
    """
    eff = parallel([Effect(ModifyGroupStatePaused(group, True)),
                    delete_divergent_flag(group.tenant_id, group.uuid, -1)])
    return with_log(eff, transaction_id=transaction_id,
                    tenant_id=group.tenant_id,
                    scaling_group_id=group.uuid).on(lambda _: None)


def pause_scaling_group(log, transaction_id, scaling_group, dispatcher):
    """
    Pauses the scaling group, causing all scaling policy executions to be
    rejected until unpaused.  This is an idempotent change, if it's already
    paused, this does not raise an error.

    :raises: :class:`NoSuchScalingGroup` if the scaling group does not exist.

    :return: None
    """
    if not tenant_is_enabled(scaling_group.tenant_id, config_value):
        raise NotImplementedError("Pause is not yet implemented")
    return perform(dispatcher,
                   conv_pause_group_eff(scaling_group, transaction_id))


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


def delete_group(log, trans_id, group, force):
    """
    Delete group based on the kind of tenant

    :param log: Bound logger
    :param str trans_id: Transaction ID of request doing this
    :param otter.models.interface.IScalingGroup scaling_group: the scaling
        group object
    :param bool force: Should group be deleted even if it has servers?

    :return: Deferred that fires with None
    :raise: `GroupNotEmptyError` if group is not empty and force=False
    """

    def check_and_delete(_group, state):
        if state.paused:
            raise GroupPausedError(
                _group.tenant_id, _group.uuid, "delete group",
                "Please use ?force=true to delete paused group")
        if state.desired == 0:
            d = trigger_convergence_deletion(log, group)
            return d.addCallback(lambda _: state)
        else:
            raise GroupNotEmptyError(group.tenant_id, group.uuid)

    if tenant_is_enabled(group.tenant_id, config_value):
        if force:
            # We don't care about servers in the group. So trigger deletion
            # since it will take precedence over other status
            d = trigger_convergence_deletion(log, group)
        else:
            # Delete only if desired is 0 which must be done with a lock to
            # ensure desired is not getting modified by another thread/node
            # when executing policy
            d = group.modify_state(
                check_and_delete,
                modify_state_reason='delete_group')
    else:
        if force:
            d = empty_group(log, trans_id, group)
            d.addCallback(lambda _: group.delete_group())
        else:
            d = group.delete_group()
    return d


def trigger_convergence_deletion(log, group):
    """
    Trigger deletion of group that belongs to convergence tenant

    :param log: Bound logger
    :param otter.models.interface.IScalingGroup scaling_group: the scaling
        group object
    """
    # Update group status and trigger convergence
    # DELETING status will take precedence over other status
    d = group.update_status(ScalingGroupStatus.DELETING)
    cs = get_convergence_starter()
    d.addCallback(
        lambda _: cs.start_convergence(log, group.tenant_id, group.uuid))
    return d


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
                launch_config=group_info['launchConfiguration']),
            modify_state_reason='empty_group')
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
        # For convergence tenants, find delta based on group's desired
        # capacity
        delta = apply_delta(log, state.desired, state, config, policy)
        # Delta could be 0, however we may still want to trigger convergence
        d = get_convergence_starter().start_convergence(
            log, scaling_group.tenant_id, scaling_group.uuid)
        if delta == 0:
            # No change in servers. Return None synchronously
            return None
        else:
            # We honor start_convergence's deferred here so that we can
            # communicate back a strong acknowledgement that convergence
            # has been triggered on the group
            return d.addCallback(lambda _: state)

    # For non-convergence tenants, the value used for desired-capacity is
    # the sum of active+pending, which is 0, so the delta ends up being
    # the min entities due to constraint calculation.
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

    :raises: :class:`NoSuchScalingGroupError` if this scaling group does not
        exist
    :raises: :class:`NoSuchPolicyError` if the policy id does not exist
    :raises: :class:`CannotExecutePolicyException` if the policy cannot be
        executed

    :raises: Some exception about why you don't want to execute the policy.
        This Exception should also have an audit log id
    """
    bound_log = log.bind(scaling_group_id=scaling_group.uuid,
                         policy_id=policy_id)
    bound_log.msg("beginning to execute scaling policy")

    if state.paused:
        raise GroupPausedError(scaling_group.tenant_id, scaling_group.uuid,
                               "execute policy {}".format(policy_id))

    # make sure that the policy (and the group) exists before doing
    # anything else
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


@do
def _is_server_in_group(group, server_id):
    """
    Given a group and server ID, determines if the server is a member of
    the group.  If it isn't, it raises a :class:`ServerNotFoundError`.
    """
    try:
        response, server_info = yield Effect(TenantScope(
            retry_effect(get_server_details(server_id),
                         retry_times(3),
                         exponential_backoff_interval(2)),
            group.tenant_id))
    except NoSuchServerError:
        raise ServerNotFoundError(group.tenant_id, group.uuid, server_id)

    group_id = group_id_from_metadata(
        get_in(('server', 'metadata'), server_info, {}))

    if group_id != group.uuid:
        raise ServerNotFoundError(group.tenant_id, group.uuid, server_id)


@do
def _can_scale_down(group, server_id):
    """
    Given a group and a server ID, determines if the group can be scaled down.
    If not, it raises a :class:`CannotDeleteServerBelowMinError`.
    """
    _, manifest = yield Effect(GetScalingGroupInfo(
        tenant_id=group.tenant_id, group_id=group.uuid))
    min_entities = manifest['groupConfiguration']['minEntities']
    state = manifest['state']

    if state.desired == min_entities:
        raise CannotDeleteServerBelowMinError(
            group.tenant_id, group.uuid, server_id, min_entities)


@do
def convergence_remove_server_from_group(
        log, transaction_id, server_id, replace, purge, group, state):
    """
    Remove a specific server from the group, optionally decrementing the
    desired capacity.

    The server may just be scheduled for deletion, or it may be evicted from
    the group by removing otter-specific metdata from the server.

    :param log: A bound logger
    :param bytes trans_id: The transaction id for this operation.
    :param bytes server_id: The id of the server to be removed.
    :param bool replace: Should the server be replaced?
    :param bool purge: Should the server be deleted from Nova?
    :param group: The scaling group to remove a server from.
    :type group: :class:`~otter.models.interface.IScalingGroup`
    :param state: The current state of the group.
    :type state: :class:`~otter.models.interface.GroupState`

    :return: The updated state.
    :rtype: deferred :class:`~otter.models.interface.GroupState`

    :raise: :class:`CannotDeleteServerBelowMinError` if the server cannot
        be deleted without replacement, and :class:`ServerNotFoundError` if
        there is no such server to be deleted.
    """
    effects = [_is_server_in_group(group, server_id)]
    if not replace:
        effects.append(_can_scale_down(group, server_id))

    # the (possibly) two checks can happen in parallel, but we want
    # ServerNotFoundError to take precedence over
    # CannotDeleteServerBelowMinError
    both_checks = yield parallel_all_errors(effects)
    for is_error, result in both_checks:
        if is_error:
            reraise(*result)

    # Remove the server
    if purge:
        eff = set_nova_metadata_item(server_id, *DRAINING_METADATA)
    else:
        eff = Effect(
            EvictServerFromScalingGroup(log=log,
                                        transaction_id=transaction_id,
                                        scaling_group=group,
                                        server_id=server_id))
    yield Effect(TenantScope(
        retry_effect(eff, retry_times(3), exponential_backoff_interval(2)),
        group.tenant_id))

    if not replace:
        yield do_return(assoc_obj(state, desired=state.desired - 1))
    else:
        yield do_return(state)


def perform_convergence_remove_from_group(
        log, trans_id, server_id, replace, purge, group, state, dispatcher):
    """
    Create the effect to remove a server from a group and performs it with
    the given dispatcher.

    :param log: A bound logger
    :param bytes trans_id: The transaction id for this operation.
    :param bytes server_id: The id of the server to be removed.
    :param bool replace: Should the server be replaced?
    :param bool purge: Should the server be deleted from Nova?
    :param group: The scaling group to remove a server from.
    :type group: :class:`~otter.models.interface.IScalingGroup`
    :param state: The current state of the group.
    :type state: :class:`~otter.models.interface.GroupState`
    :param dispatcher: A dispatcher that can perform all the effects used by
        :func:`convergence_remove_server_from_group`.

    :return: The end result of :func:`convergence_remove_server_from_group`
        (the new state).
    :rtype: deferred :class:`~otter.models.interface.GroupState`
    """
    eff = convergence_remove_server_from_group(
        log, trans_id, server_id, replace, purge, group, state)
    return perform(dispatcher, eff)


def remove_server_from_group(log, trans_id, server_id, replace, purge,
                             group, state, config_value=config_value):
    """
    Remove a specific server from the group, optionally replacing it
    with a new one, and optionally deleting the old one from Nova.

    If the old server is not deleted from Nova, otter-specific metadata
    is removed: otherwise, a different part of otter may later mistake
    the server as one that *should* still be in the group.

    :param log: A bound logger
    :param bytes trans_id: The transaction id for this operation.
    :param bytes server_id: The id of the server to be removed.
    :param bool replace: Should the server be replaced?
    :param bool purge: Should the server be deleted from Nova?
    :param group: The scaling group to remove a server from.
    :type group: :class:`~otter.models.interface.IScalingGroup`
    :param state: The current state of the group.
    :type state: :class:`~otter.models.interface.GroupState`

    :return: The updated state.
    :rtype: deferred :class:`~otter.models.interface.GroupState`
    """
    # worker case
    if not tenant_is_enabled(group.tenant_id, config_value):
        return worker_remove_server_from_group(
            log, trans_id, server_id, replace, purge, group, state)

    # convergence case - requires that the convergence dispatcher handles
    # EvictServerFromScalingGroup
    cs = get_convergence_starter()
    d = perform_convergence_remove_from_group(
        log, trans_id, server_id, replace, purge, group, state,
        cs.dispatcher)

    def kick_off_convergence(new_state):
        cs.start_convergence(log, group.tenant_id, group.uuid)
        return new_state

    return d.addCallback(kick_off_convergence)
