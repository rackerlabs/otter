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
from twisted.internet.task import deferLater

from otter.log import audit
from otter.models.interface import NoSuchScalingGroupError
from otter.supervisor import get_supervisor
from otter.json_schema.group_schemas import MAX_ENTITIES
from otter.util.deferredutils import unwrap_first_error
from otter.util.timestamp import from_timestamp


# Amount of time spaced between starting delete jobs when scaling down
DELETE_WAIT_INTERVAL = 20


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
    else:
        # delta < 0 (scale down)
        deferred = exec_scale_down(bound_log, transaction_id, state,
                                   scaling_group, -delta)

    deferred.addCallback(_do_convergence_audit_log, bound_log, delta, state)
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
            delta = calculate_delta(bound_log, state, config, policy)
            execute_bound_log = bound_log.bind(server_delta=delta)
            if delta == 0:
                execute_bound_log.msg("cooldowns checked, no change in servers")
                error_msg = "No change in servers"
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

            d.addCallback(_do_convergence_audit_log, bound_log,
                          delta, state)
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
    state.desired = max(min(desired, max_entities), config['minEntities'])
    delta = state.desired - current

    log.msg("calculating delta",
            unconstrained_desired_capacity=desired,
            constrained_desired_capacity=state.desired,
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
                          delta, state, clock=None):
    """
    Start deleting active servers jobs
    """

    # find servers to evict
    servers_to_evict = find_servers_to_evict(log, state, delta)

    # remove all the active servers to be deleted
    for server in servers_to_evict:
        state.remove_active(server['id'])

    # then start deleting those servers
    if not clock:
        from twisted.internet import reactor
        clock = reactor
    supervisor = get_supervisor()
    for i, server_info in enumerate(servers_to_evict):
        job = _DeleteJob(log, transaction_id, scaling_group, server_info, supervisor)
        d = deferLater(clock, i * DELETE_WAIT_INTERVAL, job.start)
        supervisor.deferred_pool.add(d)


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


class _DeleteJob(object):
    """
    Server deletion job
    """

    def __init__(self, log, transaction_id, scaling_group, server_info, supervisor):
        """
        :param log: a bound logger instance that can be used for logging
        :param str transaction_id: a transaction id
        :param IScalingGroup scaling_group: the scaling group from where the server
                    is deleted
        :param dict server_info: a `dict` of server info
        """
        self.log = log.bind(system='otter.job.delete', server_id=server_info['id'])
        self.trans_id = transaction_id
        self.scaling_group = scaling_group
        self.server_info = server_info
        self.supervisor = supervisor

    def start(self):
        """
        Start the job
        """
        d = self.supervisor.execute_delete_server(
            self.log, self.trans_id, self.scaling_group, self.server_info)
        d.addCallback(self._job_completed)
        d.addErrback(self._job_failed)
        self.log.msg('Started server deletion job')

    def _job_completed(self, _):
        audit(self.log).msg('Server deleted.', event_type="server.delete")

    def _job_failed(self, failure):
        # REVIEW: Logging this as err since failing to delete a server will cost
        # money to customers and affect us. We should know and try to delete it manually asap
        self.log.err(failure, 'Server deletion job failed')


class _Job(object):
    """
    Private class representing a server creation job.  This calls the supervisor
    to create one server, and also handles job completion.
    """
    def __init__(self, log, transaction_id, scaling_group, supervisor):
        """
        :param log: a bound logger instance that can be used for logging
        :param str transaction_id: a transaction id
        :param IScalingGroup scaling_group: the scaling group for which a job
            should be created
        :param dict launch_config: the launch config to scale up a server
        """
        self.log = log.bind(system='otter.job.launch')
        self.transaction_id = transaction_id
        self.scaling_group = scaling_group
        self.supervisor = supervisor
        self.job_id = None

    def start(self, launch_config):
        """
        Kick off a job by calling the supervisor with a launch config.
        """
        deferred = self.supervisor.execute_config(
            self.log, self.transaction_id, self.scaling_group, launch_config)
        deferred.addCallback(self.job_started)
        return deferred

    def _job_failed(self, f):
        """
        Job has failed. Remove the job, if it exists, and log the error.
        """
        self.log.err(f, 'Launching server failed')

        def handle_failure(group, state):
            # if it is not in pending, then the job was probably deleted before
            # it got a chance to fail.
            if self.job_id in state.pending:
                state.remove_job(self.job_id)
            return state

        d = self.scaling_group.modify_state(handle_failure)

        def ignore_error_if_group_deleted(f):
            f.trap(NoSuchScalingGroupError)
            self.log.msg("Relevant scaling group has already been deleted. "
                         "Job failure logged and ignored.")

        d.addErrback(ignore_error_if_group_deleted)
        return d

    def _job_succeeded(self, result):
        """
        Job succeeded. If the job exists, move the server from pending to active
        and log.  If not, then the job has been canceled, so delete the server.
        """
        server_id = result['id']
        log = self.log.bind(server_id=server_id)

        def handle_success(group, state):
            if self.job_id not in state.pending:
                # server was slated to be deleted when it completed building.
                # So, deleting it now
                audit(log).msg(
                    "A pending server that is no longer needed is now active, "
                    "and hence deletable.  Deleting said server.",
                    event_type="server.deletable")

                job = _DeleteJob(self.log, self.transaction_id,
                                 self.scaling_group, result, self.supervisor)
                job.start()
            else:
                state.remove_job(self.job_id)
                state.add_active(result['id'], result)
                audit(log).msg("Server is active.", event_type="server.active")
            return state

        d = self.scaling_group.modify_state(handle_success)

        def delete_if_group_deleted(f):
            f.trap(NoSuchScalingGroupError)
            audit(log).msg(
                "A pending server belonging to a deleted scaling group "
                "({scaling_group_id}) is now active, and hence deletable. "
                "Deleting said server.",
                event_type="server.deletable")

            job = _DeleteJob(self.log, self.transaction_id,
                             self.scaling_group, result, self.supervisor)
            job.start()

        d.addErrback(delete_if_group_deleted)
        return d

    def job_started(self, result):
        """
        Takes a tuple of (job_id, completion deferred), which will fire when a
        job has been completed, and marks said job as completed by removing it
        from pending.
        """
        self.job_id, completion_deferred = result
        self.log = self.log.bind(job_id=self.job_id)

        completion_deferred.addCallbacks(
            self._job_succeeded, self._job_failed)
        completion_deferred.addErrback(self.log.err)

        return self.job_id


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
        log.msg('updating state')

        for job_id in pending_results:
            state.add_job(job_id)

    if delta > 0:
        log.msg("Launching some servers.")
        supervisor = get_supervisor()
        deferreds = [
            _Job(log, transaction_id, scaling_group, supervisor).start(launch)
            for i in range(delta)
        ]

    pendings_deferred = defer.gatherResults(deferreds, consumeErrors=True)
    pendings_deferred.addCallback(_update_state)
    pendings_deferred.addErrback(unwrap_first_error)
    return pendings_deferred
