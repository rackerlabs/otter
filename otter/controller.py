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

from otter.models.interface import NoSuchScalingGroupError
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

    def _do_get_config(policy):
        deferred = scaling_group.view_config()
        return deferred.addCallback(lambda config: (config, policy))

    deferred.addCallbacks(_do_get_config)

    def _do_maybe_execute((config, policy)):
        """
        state_config_policy should be returned by ``check_cooldowns``
        """
        def mark_executed(_):
            state.mark_executed(policy_id)
            return state  # propagate the fully updated state back

        if check_cooldowns(bound_log, state, config, policy, policy_id):
            desired = calculate_desired(bound_log, state, config, policy)
            execute_bound_log = bound_log.bind(server_desired=desired)
            if desired == len(state.pending) + len(state.active):
                execute_bound_log.msg("cooldowns checked, no change in servers")
                raise CannotExecutePolicyError(scaling_group.tenant_id,
                                               scaling_group.uuid, policy_id,
                                               "No change in servers")
            state.desired = desired
            d = execute_group_transition(bound_log, scaling_group, state)
            return d.addCallback(mark_executed)
        else:
            raise CannotExecutePolicyError(scaling_group.tenant_id,
                                           scaling_group.uuid, policy_id,
                                           "Cooldowns not met.")

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


def calculate_desired(log, state, config, policy):
    """
    Calculate the desired number of servers, keeping in mind the
    minimum and maximum constraints.

    :param log: A twiggy bound log for logging
    :param dict state: the state dictionary
    :param dict config: the config dictionary
    :param dict policy: the policy dictionary

    :return: C{int} representing the desired number
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

    log.msg("calculated desired {constrained_desired_capacity}",
            unconstrained_desired_capacity=desired,
            constrained_desired_capacity=constrained,
            max_entities=max_entities, min_entities=config['minEntities'],
            server_delta=delta, current_active=len(state.active),
            current_pending=len(state.pending))
    return constrained_desired_capacity


def execute_group_transition(log, group, current):
    """
    Compare the current state w.r.t what is desired and execute actions that need
    to be performed to come to desired state
    This will be called whenever group has changed, either from user or from nova
    to ensure the group is consistent with otter
    :return: deferred that fires with updated state after all actions are taken
    """
    # TODO: Decide on handling errors from executing nova calls.
    def handle_delete_errors(failures):
        """
        Decide how to handle errors occurred from calling dependent services like
        nova/loadbalancer
        """
        # For example, If API-ratelimited, then pause the group till time expires
        # Return success if you want to scale
        pass

    def handle_scale_errors(failures):
        """
        Decide how to handle errors occurring while trying to scale up/down. It could
        be same as `handle_delete_errors` above
        """
        pass

    supervisor = get_supervisor()

    # try deleting servers in error state, building for too long or deleting for too long
    dl1 = delete_unwanted_servers(log, supervisor, group, current)

    # add/remove to load balancers
    dl2 = update_load_balancers(log, supervisor, group, current)

    d = DeferredList(dl1 + dl2, consumeErrors=True).addCallback(handle_service_errors)

    def scale(_):
        current_total = len(current.active) + len(current.pending)
        if current_total == current.desired:
            return None
        elif current_total < current.desired:
            return execute_scale_up(log, supervisor, group,
                                    current, current.desired - current_total)
        else:
            return execute_scale_down(log, supervisor, group,
                                      current, current_total - current.desired)

    return d.addCallback(scale).addCallback(handle_scale_errors).addCallback(lambda _: current)


def update_load_balancers(log, supervisor, group, state):

    deferreds = []

    def remove_server(_, server_id):
        if server_id in state.deleted:
            state.remove_deleted(server_id)
        elif server_id in state.error:
            del state.error[server_id]['lb_info']
        elif server_id in state.deleting:
            del state.deleting[server_id]['lb_info']


    # TODO: Deleted servers are required only if active servers transition to 'deleted' state
    # before going to 'deleting' state. If we can guarantee that 'active' always transition to
    # 'deleting' then 'deleted' is not required
    # Remove servers from load balancers that are no longer active
    for server_id, info in itertools.chain(
        state.error.items(), state.deleting.items(), state.deleted.items()):
        if info and info.get('lb_info'):
            d = supervisor.remove_from_load_balancers(log, group, server_id, info['lb_info'])
            d.addCallback(remove_server, server_id)
            deferreds.append(d)

    # Add active servers to load balancers that are not already there
    for server_id, info in state.active.items():
        if not (info and info.get('lb_info')):
            d = supervisor.add_to_load_balancers(log, group, server_id)
            d.addCallback(lambda lb_info, server_id: state.add_lb_info(server_id, lb_info))
            deferreds.append(d)

    return deferreds


def execute_scale_up(log, supervisor, group, state, delta):
    d = group.view_launch_config()

    def launch_servers(launch_config):
        deferreds = [
            supervisor.launch_server(log, group, launch_config)
                .addCallback(lambda s: state.add_pending(s['id'], s))
            for _i in range(delta)
        ]
        return DeferredList(deferreds, consumeErrors=True)

    return d.addCallback(launch_servers)


def execute_scale_down(log, supervisor, group, state, delta):

    def server_deleted(_, server_id):
        state.remove_active(server_id)
        state.add_deleting(server_id)

    active_delete_num = delta - len(state.pending)
    if active_delete_num > 0:
        # find oldest active servers
        sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
        servers_to_delete = sorted_servers[:delta]
        d = [supervisor.delete_server(log, group, server['id'], server['lb_info'])
                .addCallback(server_deleted, server['id'])
             for server in servers_to_delete]
        return DeferredList(deferreds, consumeErrors=True)
    else:
        # Cannot delete pending servers now.
        return defer.succeed(None)


def delete_unwanted_servers(log, supervisor, group, state):
    """
    Delete servers building for too long, deleting for too long and servers in error state

    Return DeferredList of all the delete calls
    """

    def remove_error(_, server_id):
        state.remove_error(server_id)
        state.add_deleting(server_id)

    def remove_pending(_, server_id):
        state.remove_pending(server_id)
        state.add_deleting(server_id)

    deferreds = []
    for server_id, info in state.error.items():
        d = supervisor.delete_server(
            log, group, server_id, info.get('lb_info')).addCallback(remove_error, server_id)
        # TODO: Put group in error state if delete fails
        d.addErrback(log.err, 'Could not delete server in error', server_id=server_id)
        deferreds.append(d) # TODO: schedule to execute state transition after some time
    for server_id, info in state.pending.items():
        if datetime.utcnow() - from_timestamp(info['created']) > timedelta(hours=1):
            log.msg('server building for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, info['lb_info'])
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(remove_pending, server_id)
            deferreds.append(d)
    for server_id in state.deleting:
        if datetime.utcnow() - from_timestamp(info['deleted']) > timedelta(hours=1):
            log.msg('server deleting for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, None)
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(lambda _, server_id: state.remove_deleting(server_id), server_id)
            deferreds.append(d)

    #return defer.DeferredList(deferreds, consumeErrors=True)
    return deferreds
    #return d.addCallback(collect_errors)

