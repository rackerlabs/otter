"""
Converger service

The top-level entry-points into this module are :func:`trigger_convergence` and
:obj:`Converger`.
"""

# # Note [Convergence cycles]
#
# A very abstract version of our convergence cycle:
# - CYCLE (every N seconds)
# - find all divergent flags for this node's groups
# - for each group (that's not in `currently_converging`)
#   - add to currently_converging
#   - run a single convergence iteration
#   - remove from currently_converging
# - IF group is fully converged, delete divergent flag
# - ELSE goto CYCLE
#
# Importantly for the cycle logic, divergent flags are not deleted when the
# group has not yet fully converged. This is the mechanism by which the
# "cycling" actually happens -- we repeatedly run a convergence iteration until
# we determine it's fully converged, and then we finally delete the flag. See
# [Divergent flags] for more details about the divergent flag.
#
# So: currently_converging lasts for a single *iteration*,
#     divergent flags last for a whole *cycle*.
#
# `currently_converging` is a set of group IDs that are being converged *within
# a node*. We keep track of this since we receive notifications that groups are
# divergent asynchronously with the actual convergence process. If a group is
# in that set when we notice a divergent flag, we ignore it, *without* deleting
# the divergent flag, so we will still check that group on the next cycle.


# # Note [Divergent flags]
#
# We run the convergence service on multiple servers. We want to divvy up this
# work stably between the different nodes such that a group is always converged
# by the same node -- this is to avoid accidentally running convergence
# iterations concurrently for the same group, which could lead to unnecessary
# creation/deletion of resources as the concurrent processes race against each
# other. In order to do this, we use a ZooKeeper set partitioner (see
# otter.util.zkpartitioner). All groups are stably mapped to a partitioned
# "bucket" via a simple hash/mod algorithm.
#
# In order to actually register that a group needs convergence, we create a
# ZooKeeper node with the name of the tenant and group, and convergence nodes
# watch the ZK directory and filter for groups that map to their allocated
# buckets.
#
# Marking a group divergent (or "dirty") is tricky enough that just using a
# boolean flag for "is group dirty or not" won't work, because that will allow
# a race condition that can lead to stalled convergence. Here's the scenario,
# with Otter nodes 'A' and 'B', assuming only a boolean `dirty` flag:
#
# - A: policy executed: groupN.dirty = True
# - B: converge group N (repeat until done)
# - A: policy executed: groupN.dirty = True
# - B: groupN.dirty = False
#
# Here, a policy was executed on group N twice, and A tried to mark it dirty
# twice. The problem is that when the converger node finished converging, it
# then marked it clean *after* node A tried to mark it dirty a second time.
# It's a small window of time, but if it happens at just the right moment,
# after the final iteration of convergence and before the group is marked
# clean, then the changes desired by the second policy execution will not
# happen.
#
# So instead of just a boolean flag, we'll take advantage of ZK node
# versioning. When we mark a group as dirty, we'll create a node for it if it
# doesn't exist, and if it does exist, we'll write to it with `set`. The
# content doesn't matter - the only thing that does matter is the version,
# which will be incremented on every `set` operation. On the converger side,
# when it searches for dirty groups to converge, it will remember the version
# of the node. When convergence completes, it will delete the node ONLY if the
# version hasn't changed, with a `delete(path, version)` call.
#
# The effect of this is that if any process updates the dirty flag after it's
# already been created, the node won't be deleted, so convergence will pick up
# that group again. We don't need to keep track of exactly how many times a
# group has been marked dirty (i.e. how many times a policy has been executed
# or config has changed), only if there are _any_ outstanding requests for
# convergence, since convergence always uses the most recent data.

import operator
import time
import uuid
from datetime import datetime
from functools import partial
from hashlib import sha1

import attr

from effect import Constant, Effect, Func, parallel
from effect.do import do, do_return
from effect.ref import Reference

from kazoo.exceptions import BadVersionError, NoNodeError
from kazoo.recipe.partitioner import PartitionState

from pyrsistent import pmap, pset
from pyrsistent import thaw

import six

from sumtypes import match

from toolz.functoolz import curry

from twisted.application.service import MultiService

from txeffect import exc_info_to_failure, perform

from otter.cloud_client import TenantScope
from otter.constants import CONVERGENCE_DIRTY_DIR
from otter.convergence.composition import (get_desired_server_group_state,
                                           get_desired_stack_group_state)
from otter.convergence.effecting import steps_to_effect
from otter.convergence.errors import present_reasons, structure_reason
from otter.convergence.gathering import (get_all_launch_server_data,
                                         get_all_launch_stack_data)
from otter.convergence.logging import log_steps
from otter.convergence.model import (
    ConvergenceIterationStatus,
    ServerState,
    StepResult)
from otter.convergence.planning import plan_launch_server, plan_launch_stack
from otter.convergence.transforming import get_step_limits_from_conf
from otter.log.cloudfeeds import cf_err, cf_msg
from otter.log.intents import err, msg, msg_with_time, with_log
from otter.models.intents import (
    DeleteGroup, GetScalingGroupInfo, UpdateGroupErrorReasons,
    UpdateGroupStatus, UpdateServersCache)
from otter.models.interface import NoSuchScalingGroupError, ScalingGroupStatus
from otter.util.timestamp import datetime_to_epoch
from otter.util.zk import CreateOrSet, DeleteNode, GetChildren, GetStat


def get_executor(launch_config):
    """
    Returns a ConvergenceExecutor based upon the launch_config type given.
    """
    if launch_config['type'] == 'launch_server':
        return launch_server_executor
    elif launch_config['type'] == 'launch_stack':
        return launch_stack_executor
    raise NotImplementedError


def server_to_json(server):
    """
    Convert a NovaServer to a dict representation suitable for returning to the
    end-user as a part of group state.
    """
    return {'id': server.id, 'links': thaw(server.links)}


def is_autoscale_active(server, lb_nodes):
    """
    Is the given NovaServer in all its desired LB nodes?

    :param :obj:`NovaServer` server: NovaServer being checked
    :param lb_nodes: sequence of :obj:`ILBNode`.

    :return: True if server is in LB nodes, False otherwise
    """

    def all_met(server, current_lb_nodes):
        """Determine if a server is in all the LBs it wants to be in."""
        desired_lbs = server.desired_lbs
        met_desireds = set([
            desired for desired in desired_lbs
            for node in current_lb_nodes
            if desired.equivalent_definition(node.description)])
        return desired_lbs == met_desireds

    return (server.state == ServerState.ACTIVE and
            all_met(server, [node for node in lb_nodes
                             if node.matches(server)]))


def update_servers_cache(group, now, servers, lb_nodes, include_deleted=True):
    """
    Updates the cache, adding servers, with a flag if autoscale is active on
    each one.
    :param group: scaling group
    :param list servers: list of NovaServer objects
    :param list lb_nodes: list of CLBNode objects
    :param include_deleted: Include deleted servers in cache. Defaults to True.
    """
    server_dicts = []
    for server in servers:
        sd = thaw(server.json)
        if is_autoscale_active(server, lb_nodes):
            sd["_is_as_active"] = True
        if server.state != ServerState.DELETED or include_deleted:
            server_dicts.append(sd)

    return Effect(
        UpdateServersCache(group.tenant_id, group.uuid, now, server_dicts))


@do
def _execute_steps(steps):
    """
    Given a set of steps, executes them, logs the result, and returns the worst
    priority with a list of reasons for that result.

    :return: a tuple of (:class:`StepResult` constant., list of reasons)
    """
    if len(steps) > 0:
        results = yield steps_to_effect(steps)

        severity = [StepResult.FAILURE, StepResult.RETRY,
                    StepResult.LIMITED_RETRY, StepResult.SUCCESS]
        priority = sorted(results,
                          key=lambda (status, reasons): severity.index(status))
        worst_status = priority[0][0]
        results_to_log = [
            {'step': step,
             'result': result,
             'reasons': map(structure_reason, reasons)}
            for step, (result, reasons) in
            zip(steps, results)
        ]
        reasons = reduce(operator.add,
                         (x[1] for x in results if x[0] == worst_status))
    else:
        worst_status = StepResult.SUCCESS
        results_to_log = reasons = []

    yield msg('execute-convergence-results',
              results=results_to_log,
              worst_status=worst_status.name)
    yield do_return((worst_status, reasons))


@do
def convergence_exec_data(tenant_id, group_id, now, get_executor):
    """
    Get data required while executing convergence
    """
    sg_eff = Effect(GetScalingGroupInfo(tenant_id=tenant_id,
                                        group_id=group_id))

    (scaling_group, manifest) = yield sg_eff

    group_state = manifest['state']
    launch_config = manifest['launchConfiguration']

    executor = get_executor(launch_config)

    resources = yield executor.gather(tenant_id, group_id, now)

    if group_state.status == ScalingGroupStatus.DELETING:
        desired_capacity = 0
    else:
        desired_capacity = group_state.desired
        yield executor.update_cache(scaling_group, now, **resources)

    desired_group_state = executor.get_desired_group_state(
        group_id, launch_config, desired_capacity)

    yield do_return((executor, scaling_group, group_state, desired_group_state,
                     resources))


def _clean_waiting(waiting, group_id):
    return waiting.modify(
        lambda group_iterations: group_iterations.discard(group_id))


@do
def execute_convergence(tenant_id, group_id, build_timeout, waiting,
                        limited_retry_iterations, step_limits,
                        get_executor=get_executor):
    """
    Gather data, plan a convergence, save active and pending servers to the
    group state, and then execute the convergence.

    :param str tenant_id: the tenant ID for the group to converge
    :param str group_id: the ID of the group to be converged
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
    :param Reference waiting: pmap of waiting groups
    :param int limited_retry_iterations: number of iterations to wait for
        LIMITED_RETRY steps
    :param dict step_limits: Mapping of step class to number of executions
        allowed in a convergence cycle
    :param callable get_executor: like :func`get_executor`, used for testing.

    :return: Effect of :obj:`ConvergenceIterationStatus`.
    :raise: :obj:`NoSuchScalingGroupError` if the group doesn't exist.
    """
    clean_waiting = _clean_waiting(waiting, group_id)
    # Gather data
    yield msg("begin-convergence")
    now_dt = yield Effect(Func(datetime.utcnow))
    all_data = yield msg_with_time(
        "gather-convergence-data",
        convergence_exec_data(tenant_id, group_id, now_dt,
                              get_executor=get_executor))
    (executor, scaling_group, group_state, desired_group_state,
     resources) = all_data

    # prepare plan
    steps = executor.plan(desired_group_state, datetime_to_epoch(now_dt),
                          build_timeout, step_limits, **resources)
    yield log_steps(steps)

    # Execute plan
    yield msg('execute-convergence',
              steps=steps, now=now_dt, desired=desired_group_state,
              **resources)
    worst_status, reasons = yield _execute_steps(steps)

    if worst_status != StepResult.LIMITED_RETRY:
        # If we're not waiting any more, there's no point in keeping track of
        # the group
        yield clean_waiting

    # Handle the status from execution
    if worst_status == StepResult.SUCCESS:
        result = yield convergence_succeeded(
            executor, scaling_group, group_state, resources, now_dt)
    elif worst_status == StepResult.FAILURE:
        result = yield convergence_failed(scaling_group, reasons)
    elif worst_status is StepResult.LIMITED_RETRY:
        # We allow further iterations to proceed as long as we haven't been
        # waiting for a LIMITED_RETRY for N consecutive iterations.
        current_iterations = (yield waiting.read()).get(group_id, 0)
        if current_iterations > limited_retry_iterations:
            yield msg('converge-limited-retry-too-long')
            yield clean_waiting
            # Prefix "Timed out" to all limited retry reasons
            result = yield convergence_failed(scaling_group, reasons, True)
        else:
            yield waiting.modify(
                lambda group_iterations:
                    group_iterations.set(group_id, current_iterations + 1))
            result = ConvergenceIterationStatus.Continue()
    else:
        result = ConvergenceIterationStatus.Continue()
    yield do_return(result)


def update_stacks_cache(scaling_group, now, stacks, include_deleted=True):
    return Effect(Func(lambda: None))


@do
def convergence_succeeded(executor, scaling_group, group_state, resources,
                          now):
    """
    Handle convergence success
    """
    if group_state.status == ScalingGroupStatus.DELETING:
        # servers have been deleted. Delete the group for real
        yield Effect(DeleteGroup(tenant_id=scaling_group.tenant_id,
                                 group_id=scaling_group.uuid))
        yield do_return(ConvergenceIterationStatus.GroupDeleted())
    elif group_state.status == ScalingGroupStatus.ERROR:
        yield Effect(UpdateGroupStatus(scaling_group=scaling_group,
                                       status=ScalingGroupStatus.ACTIVE))
        yield cf_msg('group-status-active',
                     status=ScalingGroupStatus.ACTIVE.name)
    # update servers cache with latest servers
    yield executor.update_cache(scaling_group, now, include_deleted=False,
                                **resources)
    yield do_return(ConvergenceIterationStatus.Stop())


@do
def convergence_failed(scaling_group, reasons, timedout=False):
    """
    Handle convergence failure
    """
    yield Effect(UpdateGroupStatus(scaling_group=scaling_group,
                                   status=ScalingGroupStatus.ERROR))
    presented_reasons = sorted(present_reasons(reasons))
    if len(presented_reasons) == 0:
        presented_reasons = [u"Unknown error occurred"]
    elif timedout:
        presented_reasons = ["Timed out: {}".format(reason)
                             for reason in presented_reasons]
    yield cf_err(
        'group-status-error', status=ScalingGroupStatus.ERROR.name,
        reasons=presented_reasons)
    yield Effect(UpdateGroupErrorReasons(scaling_group, presented_reasons))
    yield do_return(ConvergenceIterationStatus.Stop())


def format_dirty_flag(tenant_id, group_id):
    """Format a dirty flag ZooKeeper node name."""
    return tenant_id + '_' + group_id


def parse_dirty_flag(flag):
    """Parse a dirty flag ZooKeeper node name into (tenant_id, group_id)."""
    return flag.split('_', 1)


def mark_divergent(tenant_id, group_id):
    """
    Indicate that a group should be converged.

    This doesn't actually do the work of convergence -- it simply records a
    note that the group is divergent.

    :param tenant_id: tenant ID that owns the group.
    :param group_id: ID of the group to converge.

    :return: an Effect which succeeds when the information has been
        recorded.
    """
    # See note [Divergent flags]
    flag = format_dirty_flag(tenant_id, group_id)
    path = CONVERGENCE_DIRTY_DIR + '/' + flag
    eff = Effect(CreateOrSet(path=path, content='dirty'))
    return eff


@do
def delete_divergent_flag(tenant_id, group_id, version):
    """
    Delete the dirty flag, if its version hasn't changed. See note [Divergent
    flags] for more info.

    :return: Effect of None.
    """
    flag = format_dirty_flag(tenant_id, group_id)
    path = CONVERGENCE_DIRTY_DIR + '/' + flag
    fields = dict(path=path, dirty_version=version)
    try:
        yield Effect(DeleteNode(path=path, version=version))
    except BadVersionError:
        # BadVersionError shouldn't be logged as an error because it's an
        # expected occurrence any time convergence is requested multiple times
        # rapidly.
        yield msg('mark-clean-skipped', **fields)
    except NoNodeError:
        yield msg('mark-clean-not-found', **fields)
    except Exception:
        yield err(None, 'mark-clean-failure', **fields)
    else:
        yield msg('mark-clean-success')


@curry
def log_and_raise(msg, exc_info):
    """
    Log error and raise it
    """
    eff = err(exc_info_to_failure(exc_info), msg)
    return eff.on(lambda _: six.reraise(*exc_info))


def trigger_convergence(tenant_id, group_id):
    """
    Trigger convergence on a scaling group
    """
    eff = mark_divergent(tenant_id, group_id)
    return eff.on(success=lambda _: msg("mark-dirty-success"),
                  error=log_and_raise("mark-dirty-failure"))




class ConcurrentError(Exception):
    """Tried to run an effect concurrently when it shouldn't be."""


@do
def non_concurrently(locks, key, eff):
    """
    Run some Effect non-concurrently.

    :param Reference locks: A reference to a PSet that will be used to record
        which operations are currently being executed.
    :param key: the key to use for this particular operation, which will be
        stored in ``locks``
    :param Effect eff: the effect to execute.

    :return: Effect with the result of ``eff``, or an error of
        :obj:`ConcurrentError` if the given key already has an associated
        effect being performed.
    """
    if key in (yield locks.read()):
        raise ConcurrentError(key)
    yield locks.modify(lambda cc: cc.add(key))
    try:
        result = yield eff
    finally:
        yield locks.modify(lambda cc: cc.remove(key))
    yield do_return(result)


def get_my_divergent_groups(my_buckets, all_buckets, divergent_flags):
    """
    Given a list of dirty-flags, filter out the ones that aren't associated
    with our buckets and return them as structured data.

    :param my_buckets: collection of buckets allocated to this node
    :param all_buckets: collection of all buckets
    :param divergent_flags: divergent flags that were found in zookeeper.

    :returns: list of dicts, where each dict has ``tenant_id``,
        ``group_id``, and ``dirty-flag`` keys.
    """
    def structure_info(path):
        # Names of the dirty flags are {tenant_id}_{group_id}.
        tenant, group = parse_dirty_flag(path)
        return {'tenant_id': tenant,
                'group_id': group,
                'dirty-flag': CONVERGENCE_DIRTY_DIR + '/' + path}

    dirty_info = map(structure_info, divergent_flags)
    num_buckets = len(all_buckets)
    converging = [
        info for info in dirty_info
        if bucket_of_tenant(info['tenant_id'], num_buckets) in my_buckets]
    return converging


def eff_finally(eff, after_eff):
    """Run some effect after another effect, whether it succeeds or fails."""
    return eff.on(success=lambda r: after_eff.on(lambda _: r),
                  error=lambda e: after_eff.on(lambda _: six.reraise(*e)))


@do
def converge_one_group(currently_converging, recently_converged, waiting,
                       tenant_id, group_id, version,
                       build_timeout, limited_retry_iterations, step_limits,
                       execute_convergence=execute_convergence):
    """
    Converge one group, non-concurrently, and clean up the dirty flag when
    done.

    :param Reference currently_converging: pset of currently converging groups
    :param Reference recently_converged: pmap of recently converged groups
    :param Reference waiting: pmap of waiting groups
    :param str tenant_id: the tenant ID of the group that is converging
    :param str group_id: the ID of the group that is converging
    :param version: version number of ZNode of the group's dirty flag
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
    :param int limited_retry_iterations: number of iterations to wait for
        LIMITED_RETRY steps
    :param dict step_limits: Mapping of step class to number of executions
        allowed in a convergence cycle
    :param callable execute_convergence: like :func`execute_convergence`, to
        be used for test injection only
    """
    mark_recently_converged = Effect(Func(time.time)).on(
        lambda time_done: recently_converged.modify(
            lambda rcg: rcg.set(group_id, time_done)))
    cvg = eff_finally(
        execute_convergence(tenant_id, group_id, build_timeout, waiting,
                            limited_retry_iterations, step_limits),
        mark_recently_converged)

    try:
        result = yield non_concurrently(currently_converging, group_id, cvg)
    except ConcurrentError:
        # We don't need to spam the logs about this, it's to be expected
        return
    except NoSuchScalingGroupError:
        yield err(None, 'converge-fatal-error')
        yield _clean_waiting(waiting, group_id)
        yield delete_divergent_flag(tenant_id, group_id, version)
        return
    except Exception:
        # We specifically don't clean up the dirty flag in the case of
        # unexpected errors, so convergence will be retried.
        yield err(None, 'converge-non-fatal-error')
    else:
        @match(ConvergenceIterationStatus)
        class clean_up(object):
            def Continue():
                return Effect(Constant(None))

            def Stop():
                return delete_divergent_flag(tenant_id, group_id, version)

            def GroupDeleted():
                # Delete the divergent flag to avoid any queued-up convergences
                # that will imminently fail.
                return delete_divergent_flag(tenant_id, group_id, -1)
        yield clean_up(result)


@do
def converge_all_groups(
        currently_converging, recently_converged, waiting,
        my_buckets, all_buckets,
        divergent_flags, build_timeout, interval,
        limited_retry_iterations, step_limits,
        converge_one_group=converge_one_group):
    """
    Check for groups that need convergence and which match up to the
    buckets we've been allocated.

    :param Reference currently_converging: pset of currently converging groups
    :param Reference recently_converged: pmap of group ID to time last
        convergence finished
    :param Reference waiting: pmap of group ID to number of iterations already
        waited
    :param my_buckets: The buckets that should be checked for group IDs to
        converge on.
    :param all_buckets: The set of all buckets that can be checked for group
        IDs to converge on.  ``my_buckets`` should be a subset of this.
    :param divergent_flags: divergent flags that were found in zookeeper.
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
    :param number interval: number of seconds between attempts at convergence.
        Groups will not be converged if less than this amount of time has
        passed since the end of its last convergence.
    :param int limited_retry_iterations: number of iterations to wait for
        LIMITED_RETRY steps
    :param dict step_limits: Mapping of step class to number of executions
        allowed in a convergence cycle
    :param callable converge_one_group: function to use to converge a single
        group - to be used for test injection only
    """
    group_infos = get_my_divergent_groups(
        my_buckets, all_buckets, divergent_flags)
    # filter out currently converging groups
    cc = yield currently_converging.read()
    group_infos = [info for info in group_infos if info['group_id'] not in cc]
    if not group_infos:
        return
    yield msg('converge-all-groups', group_infos=group_infos,
              currently_converging=list(cc))

    @do
    def converge(tenant_id, group_id, dirty_flag):
        stat = yield Effect(GetStat(dirty_flag))
        # If the node disappeared, ignore it. `stat` will be None here if the
        # divergent flag was discovered only after the group is removed from
        # currently_converging, but before the divergent flag is deleted, and
        # then the deletion happens, and then our GetStat happens. This
        # basically means it happens when one convergence is starting as
        # another one for the same group is ending.
        if stat is None:
            yield msg('converge-divergent-flag-disappeared', znode=dirty_flag)
        else:
            eff = converge_one_group(currently_converging, recently_converged,
                                     waiting,
                                     tenant_id, group_id,
                                     stat.version, build_timeout,
                                     limited_retry_iterations, step_limits)
            result = yield Effect(TenantScope(eff, tenant_id))
            yield do_return(result)

    recent_groups = yield get_recently_converged_groups(recently_converged,
                                                        interval)
    effs = []
    for info in group_infos:
        tenant_id, group_id = info['tenant_id'], info['group_id']
        if group_id in recent_groups:
            # Don't converge a group if it has recently been converged.
            continue
        eff = converge(tenant_id, group_id, info['dirty-flag'])
        effs.append(
            with_log(eff, tenant_id=tenant_id, scaling_group_id=group_id))

    yield do_return(parallel(effs))


@do
def get_recently_converged_groups(recently_converged, interval):
    """
    Return a list of recently converged groups, and garbage-collect any groups
    in the recently_converged map that are no longer 'recent'.
    """
    # STM would be cool but this is synchronous so whatever
    recent = yield recently_converged.read()
    now = yield Effect(Func(time.time))
    to_remove = [group for group in recent if now - recent[group] > interval]
    cleaned = reduce(lambda m, g: m.remove(g), to_remove, recent)
    if recent != cleaned:
        yield recently_converged.modify(lambda _: cleaned)
    yield do_return(cleaned.keys())


def _stable_hash(s):
    """Get a stable hash of a string as an integer."""
    # :func:`hash` is not stable with different pythons/architectures.
    return int(sha1(s).hexdigest(), 16)


def bucket_of_tenant(tenant, num_buckets):
    """
    Return the bucket associated with the given tenant.

    :param str tenant: tenant ID
    :param int num_buckets: global number of buckets
    """
    return _stable_hash(tenant) % num_buckets


class Converger(MultiService):
    """
    A service that searches for groups that need converging and then does the
    work of converging them.

    This service is pretty much just a wrapper for :func:`execute_convergence`,
    with a few important layers above it:

    - virtual "buckets" are partitioned between nodes running this service by
      using ZooKeeper (thus, this service could/should be run separately from
      the API). group IDs are deterministically mapped to these buckets.
    - we repeatedly check for 'dirty flags' created by
      :func:`trigger_convergence` service, and determine if they're "ours" with
      the partitioner.
    - we ensure we don't execute convergence for the same group concurrently.
    """

    def __init__(self, log, dispatcher, num_buckets, partitioner_factory,
                 build_timeout, interval,
                 limited_retry_iterations, step_limits,
                 converge_all_groups=converge_all_groups):
        """
        :param log: a bound log
        :param dispatcher: The dispatcher to use to perform effects.
        :param int buckets: the number of logical `buckets` which are be
            shared between all Otter nodes running this service. The buckets
            will be partitioned up between nodes to detirmine which nodes
            should work on which groups.
        :param partitioner_factory: Callable of (all_buckets, log, callback)
            which should create an :obj:`Partitioner` to distribute the
            buckets.
        :param number build_timeout: number of seconds to wait for servers to
            be in building before it's is timed out and deleted
        :param interval: Interval between convergence steps, per group.
        :param callable converge_all_groups: like :func:`converge_all_groups`,
            to be used for test injection only
        :param int limited_retry_iterations: number of iterations to wait for
            LIMITED_RETRY steps
        :param dict step_limits: Mapping of step name to number of executions
            allowed in a convergence cycle
        """
        MultiService.__init__(self)
        self.log = log.bind(otter_service='converger')
        self._dispatcher = dispatcher
        self._buckets = range(num_buckets)
        self.partitioner = partitioner_factory(
            buckets=self._buckets, log=self.log,
            got_buckets=self.buckets_acquired)
        self.partitioner.setServiceParent(self)
        self.build_timeout = build_timeout
        self._converge_all_groups = converge_all_groups
        self.interval = interval
        self.limited_retry_iterations = limited_retry_iterations
        self.step_limits = get_step_limits_from_conf(step_limits)

        # ephemeral mutable state
        self.currently_converging = Reference(pset())
        self.recently_converged = Reference(pmap())
        # Groups we're waiting on temporarily, and may give up on.
        self.waiting = Reference(pmap())  # {group_id: num_iterations_waited}

    def _converge_all(self, my_buckets, divergent_flags):
        """Run :func:`converge_all_groups` and log errors."""
        eff = self._converge_all_groups(
            self.currently_converging, self.recently_converged,
            self.waiting,
            my_buckets, self._buckets, divergent_flags, self.build_timeout,
            self.interval, self.limited_retry_iterations, self.step_limits)
        return eff.on(
            error=lambda e: err(
                exc_info_to_failure(e), 'converge-all-groups-error'))

    def _with_conv_runid(self, eff):
        """
        Return Effect wrapped with converger_run_id log field
        """
        return Effect(Func(uuid.uuid4)).on(str).on(
            lambda uid: with_log(eff, otter_service='converger',
                                 converger_run_id=uid))

    def buckets_acquired(self, my_buckets):
        """
        Get dirty flags from zookeeper and run convergence with them.

        This is used as the partitioner callback.
        """
        ceff = Effect(GetChildren(CONVERGENCE_DIRTY_DIR)).on(
            partial(self._converge_all, my_buckets))
        # Return deferred as 1-element tuple for testing only.
        # Returning deferred would block otter from shutting down until
        # it is fired which we don't need to do since convergence is itempotent
        # and will be triggered in next start of otter
        return (perform(self._dispatcher, self._with_conv_runid(ceff)), )

    def divergent_changed(self, children):
        """
        ZooKeeper children-watch callback that lets this service know when the
        divergent groups have changed. If any of the divergent flags are for
        tenants associated with this service's buckets, a convergence will be
        triggered.
        """
        if self.partitioner.get_current_state() != PartitionState.ACQUIRED:
            return
        my_buckets = self.partitioner.get_current_buckets()
        changed_buckets = set(
            bucket_of_tenant(parse_dirty_flag(child)[0], len(self._buckets))
            for child in children)
        if set(my_buckets).intersection(changed_buckets):
            # the return value is ignored, but we return this for testing
            eff = self._converge_all(my_buckets, children)
            return perform(self._dispatcher, self._with_conv_runid(eff))


@attr.s
class ConvergenceExecutor(object):
    """
    A bag of methods to enable configurable logic for different types of launch
    configurations.
    """
    gather = attr.ib()
    plan = attr.ib()
    get_desired_group_state = attr.ib()
    update_cache = attr.ib()


launch_server_executor = ConvergenceExecutor(
    gather=get_all_launch_server_data,
    plan=plan_launch_server,
    get_desired_group_state=get_desired_server_group_state,
    update_cache=update_servers_cache)


launch_stack_executor = ConvergenceExecutor(
    gather=get_all_launch_stack_data,
    plan=plan_launch_stack,
    get_desired_group_state=get_desired_stack_group_state,
    update_cache=update_stacks_cache)
