"""
Converger service

The top-level entry-points into this module are :obj:`ConvergenceStarter` and
:obj:`Converger`.
"""

import operator
import uuid
from datetime import datetime
from functools import partial
from hashlib import sha1

from effect import Effect, FirstError, Func, catch, parallel
from effect.do import do, do_return
from effect.ref import Reference

from kazoo.exceptions import BadVersionError
from kazoo.recipe.partitioner import PartitionState

from pyrsistent import pset
from pyrsistent import thaw

import six

from toolz.dicttoolz import merge

from twisted.application.service import MultiService

from txeffect import exc_info_to_failure, perform

from otter.cloud_client import TenantScope
from otter.constants import CONVERGENCE_DIRTY_DIR
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.errors import present_reasons, structure_reason
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.logging import log_steps
from otter.convergence.model import ServerState, StepResult
from otter.convergence.planning import plan
from otter.log.cloudfeeds import cf_err, cf_msg
from otter.log.intents import err, msg, with_log
from otter.models.intents import (
    DeleteGroup, GetScalingGroupInfo, UpdateGroupStatus, UpdateServersCache)
from otter.models.interface import NoSuchScalingGroupError, ScalingGroupStatus
from otter.util.timestamp import datetime_to_epoch
from otter.util.zk import CreateOrSet, DeleteNode, GetChildren, GetStat


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


def update_cache(group, servers, lb_nodes, now):
    """
    :param group: scaling group
    :param list servers: list of NovaServer objects
    """
    server_dicts = []
    for server in servers:
        sd = thaw(server.json)
        if is_autoscale_active(server, lb_nodes):
            sd["_is_as_active"] = True
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

        severity = [StepResult.FAILURE, StepResult.RETRY, StepResult.SUCCESS]
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
def convergence_exec_data(tenant_id, group_id, now, get_all_convergence_data):
    """
    Get data required while executing convergence
    """
    sg_eff = Effect(GetScalingGroupInfo(tenant_id=tenant_id,
                                        group_id=group_id))
    gather_eff = get_all_convergence_data(tenant_id, group_id, now)
    try:
        data = yield parallel([sg_eff, gather_eff])
    except FirstError as fe:
        six.reraise(*fe.exc_info)
    [(scaling_group, manifest), (servers, lb_nodes)] = data

    group_state = manifest['state']
    launch_config = manifest['launchConfiguration']

    if group_state.status == ScalingGroupStatus.DELETING:
        desired_capacity = 0
    else:
        desired_capacity = group_state.desired
        yield update_cache(scaling_group, servers, lb_nodes, now)

    desired_group_state = get_desired_group_state(
        group_id, launch_config, desired_capacity)

    yield do_return((scaling_group, group_state, desired_group_state,
                     servers, lb_nodes))


@do
def execute_convergence(tenant_id, group_id, build_timeout,
                        get_all_convergence_data=get_all_convergence_data,
                        plan=plan):
    """
    Gather data, plan a convergence, save active and pending servers to the
    group state, and then execute the convergence.

    :param str tenant_id: the tenant ID for the group to converge
    :param str group_id: the ID of the group to be converged
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
    :param callable get_all_convergence_data: like
        :func`get_all_convergence_data`, used for testing.
    :param callable plan: like :func:`plan`, to be used for test injection only

    :return: Effect of two-tuple of (most severe StepResult, group status).
        When group status is None it means the group has been successfully
        deleted.
    :raise: :obj:`NoSuchScalingGroupError` if the group doesn't exist.
    """
    # Gather data
    now_dt = yield Effect(Func(datetime.utcnow))
    all_data = yield convergence_exec_data(tenant_id, group_id, now_dt,
                                           get_all_convergence_data)
    (scaling_group, group_state, desired_group_state,
     servers, lb_nodes) = all_data

    # prepare plan
    steps = plan(desired_group_state, servers, lb_nodes,
                 datetime_to_epoch(now_dt), build_timeout)
    yield log_steps(steps)

    # Execute plan
    yield msg('execute-convergence',
              servers=servers, lb_nodes=lb_nodes, steps=steps, now=now_dt,
              desired=desired_group_state)
    worst_status, reasons = yield _execute_steps(steps)

    # Handle the status from execution
    result_status = group_state.status
    if worst_status == StepResult.SUCCESS:
        result_status = yield convergence_succeeded(
            scaling_group, group_state, servers, now_dt)
    elif worst_status == StepResult.FAILURE:
        result_status = yield convergence_failed(scaling_group, reasons)

    yield do_return((worst_status, result_status))


@do
def convergence_succeeded(scaling_group, group_state, servers, now):
    """
    Handle convergence success
    """
    if group_state.status == ScalingGroupStatus.DELETING:
        # servers have been deleted. Delete the group for real
        yield Effect(DeleteGroup(tenant_id=scaling_group.tenant_id,
                                 group_id=scaling_group.uuid))
        yield do_return(None)
    elif group_state.status == ScalingGroupStatus.ERROR:
        yield Effect(UpdateGroupStatus(scaling_group=scaling_group,
                                       status=ScalingGroupStatus.ACTIVE))
        yield cf_msg('group-status-active',
                     status=ScalingGroupStatus.ACTIVE.name)
    # update servers cache with latest servers
    yield Effect(
        UpdateServersCache(
            scaling_group.tenant_id, scaling_group.uuid, now,
            [merge(thaw(s.json), {"_is_as_active": True})
                for s in servers if s.state != ServerState.DELETED]))
    yield do_return(ScalingGroupStatus.ACTIVE)


@do
def convergence_failed(scaling_group, reasons):
    """
    Handle convergence failure
    """
    yield Effect(UpdateGroupStatus(scaling_group=scaling_group,
                                   status=ScalingGroupStatus.ERROR))
    yield cf_err(
        'group-status-error', status=ScalingGroupStatus.ERROR.name,
        reasons='; '.join(sorted(present_reasons(reasons))))
    yield do_return(ScalingGroupStatus.ERROR)


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
    # This is tricky enough that just using a boolean flag for "is group
    # dirty or not" won't work, because that will allow a race condition
    # that can lead to stalled convergence. Here's the scenario, with Otter
    # nodes 'A' and 'B', assuming only a boolean `dirty` flag:

    # - A: policy executed: groupN.dirty = True
    # -               B: converge group N (repeat until done)
    # - A: policy executed: groupN.dirty = True
    # -               B: groupN.dirty = False

    # Here, a policy was executed on group N twice, and A tried to mark it
    # dirty twice. The problem is that when the converger node finished
    # converging, it then marked it clean *after* node A tried to mark it dirty
    # a second time. It's a small window of time, but if it happens at just the
    # right moment, after the final iteration of convergence and before the
    # group is marked clean, then the changes desired by the second policy
    # execution will not happen.

    # So instead of just a boolean flag, we'll take advantage of ZK node
    # versioning. When we mark a group as dirty, we'll create a node for it
    # if it doesn't exist, and if it does exist, we'll write to it with
    # `set`. The content doesn't matter - the only thing that does matter
    # is the version, which will be incremented on every `set`
    # operation. On the converger side, when it searches for dirty groups
    # to converge, it will remember the version of the node. When
    # convergence completes, it will delete the node ONLY if the version
    # hasn't changed, with a `delete(path, version)` call.

    # The effect of this is that if any process updates the dirty flag
    # after it's already been created, the node won't be deleted, so
    # convergence will pick up that group again. We don't need to keep
    # track of exactly how many times a group has been marked dirty
    # (i.e. how many times a policy has been executed or config has
    # changed), only if there are _any_ outstanding requests for
    # convergence, since convergence always uses the most recent data.

    flag = format_dirty_flag(tenant_id, group_id)
    path = CONVERGENCE_DIRTY_DIR + '/' + flag
    eff = Effect(CreateOrSet(path=path, content='dirty'))
    return eff


def delete_divergent_flag(tenant_id, group_id, version):
    """
    Delete the dirty flag, if its version hasn't changed. See comment in
    :func:`mark_divergent` for more info.

    :return: Effect of None.
    """
    flag = format_dirty_flag(tenant_id, group_id)
    path = CONVERGENCE_DIRTY_DIR + '/' + flag
    return Effect(DeleteNode(path=path, version=version)).on(
        success=lambda r: msg('mark-clean-success'),
        # BadVersionError shouldn't be logged as an error because it's an
        # expected occurrence any time convergence is requested multiple times
        # rapidly.
        error=catch(
            BadVersionError, lambda e: msg('mark-clean-skipped',
                                           path=path, dirty_version=version))
    ).on(
        error=lambda e: err(exc_info_to_failure(e), 'mark-clean-failure',
                            path=path, dirty_version=version))


class ConvergenceStarter(object):
    """
    A service that allows indicating that a group has diverged and needs
    convergence, but does not do the converging itself (see :obj:`Converger`
    for that).
    """
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher

    def start_convergence(self, log, tenant_id, group_id, perform=perform):
        """Record that a group needs converged by creating a ZooKeeper node."""
        log = log.bind(tenant_id=tenant_id, scaling_group_id=group_id)
        eff = mark_divergent(tenant_id, group_id)
        d = perform(self.dispatcher, eff)

        def success(r):
            log.msg('mark-dirty-success')
            return r  # The result is ignored normally, but return it for tests
        d.addCallbacks(success, log.err, errbackArgs=('mark-dirty-failure',))
        return d


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


@do
def converge_one_group(currently_converging, tenant_id, group_id, version,
                       build_timeout, execute_convergence=execute_convergence):
    """
    Converge one group, non-concurrently, and clean up the dirty flag when
    done.

    :param Reference currently_converging: pset of currently converging groups
    :param str tenant_id: the tenant ID of the group that is converging
    :param str group_id: the ID of the group that is converging
    :param version: version number of ZNode of the group's dirty flag
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
    :param callable execute_convergence: like :func`execute_convergence`, to
        be used for test injection only
    """
    eff = execute_convergence(tenant_id, group_id, build_timeout)
    try:
        result = yield non_concurrently(currently_converging, group_id, eff)
    except ConcurrentError:
        # We don't need to spam the logs about this, it's to be expected
        return
    except NoSuchScalingGroupError:
        yield err(None, 'converge-fatal-error')
        yield delete_divergent_flag(tenant_id, group_id, version)
        return
    except Exception:
        # We specifically don't clean up the dirty flag in the case of
        # unexpected errors, so convergence will be retried.
        yield err(None, 'converge-non-fatal-error')
    else:
        if result[0] in (StepResult.FAILURE, StepResult.SUCCESS):
            # In order to avoid doing extra work and reporting spurious errors,
            # if the group status is None it means the group has successfully
            # been deleted by execute_convergence. And so we will
            # unconditionally delete the divergent flag to avoid any further
            # queued-up convergences that will imminently fail.
            if result[1] is None:
                version = -1
            yield delete_divergent_flag(tenant_id, group_id, version)


@do
def converge_all_groups(currently_converging, my_buckets, all_buckets,
                        divergent_flags, build_timeout,
                        converge_one_group=converge_one_group):
    """
    Check for groups that need convergence and which match up to the
    buckets we've been allocated.

    :param Reference currently_converging: pset of currently converging groups
    :param my_buckets: The buckets that should be checked for group IDs to
        converge on.
    :param all_buckets: The set of all buckets that can be checked for group
        IDs to converge on.  ``my_buckets`` should be a subset of this.
    :param divergent_flags: divergent flags that were found in zookeeper.
    :param number build_timeout: number of seconds to wait for servers to be in
        building before it's is timed out and deleted
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

    def converge(tenant_id, group_id, dirty_flag):
        def got_stat(stat):
            # If the node disappeared, ignore it. `stat` will be None here if
            # the divergent flag was discovered only after the group is removed
            # from currently_converging, but before the divergent flag is
            # deleted, and then the deletion happens, and then our GetStat
            # happens. This basically means it happens when one convergence is
            # starting as another one for the same group is ending.
            if stat is None:
                return msg('converge-divergent-flag-disappeared',
                           znode=dirty_flag)
            else:
                return Effect(TenantScope(
                    converge_one_group(currently_converging,
                                       tenant_id, group_id, stat.version,
                                       build_timeout),
                    tenant_id))
        return Effect(GetStat(dirty_flag)).on(got_stat)

    effs = []
    for info in group_infos:
        tenant_id, group_id = info['tenant_id'], info['group_id']
        eff = converge(tenant_id, group_id, info['dirty-flag'])
        effs.append(
            with_log(eff, tenant_id=tenant_id, scaling_group_id=group_id))

    yield do_return(parallel(effs))


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
    - we repeatedly check for 'dirty flags' created by the
      :obj:`ConvergenceStarter` service, and determine if they're "ours" with
      the partitioner.
    - we ensure we don't execute convergence for the same group concurrently.
    """

    def __init__(self, log, dispatcher, num_buckets, partitioner_factory,
                 build_timeout, converge_all_groups=converge_all_groups):
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
        :param callable converge_all_groups: like :func:`converge_all_groups`,
            to be used for test injection only
        """
        MultiService.__init__(self)
        self.log = log.bind(otter_service='converger')
        self._dispatcher = dispatcher
        self._buckets = range(num_buckets)
        self.partitioner = partitioner_factory(
            buckets=self._buckets, log=self.log,
            got_buckets=self.buckets_acquired)
        self.partitioner.setServiceParent(self)
        self.currently_converging = Reference(pset())
        self.build_timeout = build_timeout
        self._converge_all_groups = converge_all_groups

    def _converge_all(self, my_buckets, divergent_flags):
        """Run :func:`converge_all_groups` and log errors."""
        eff = self._converge_all_groups(self.currently_converging,
                                        my_buckets, self._buckets,
                                        divergent_flags, self.build_timeout)
        return eff.on(
            error=lambda e: err(
                exc_info_to_failure(e), 'converge-all-groups-error'))

    def _with_conv_runid(self, eff):
        """
        Return Effect wrapped with converger_run_id log field
        """
        return Effect(Func(uuid.uuid1)).on(str).on(
            lambda uid: with_log(eff, otter_service='converger',
                                 converger_run_id=uid))

    def buckets_acquired(self, my_buckets):
        """
        Get dirty flags from zookeeper and run convergence with them.

        This is used as the partitioner callback.
        """
        ceff = Effect(GetChildren(CONVERGENCE_DIRTY_DIR)).on(
            partial(self._converge_all, my_buckets))
        return perform(self._dispatcher, self._with_conv_runid(ceff))

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

# We're using a global for now because it's difficult to thread a new parameter
# all the way through the REST objects to the controller code, where this
# service is used.
_convergence_starter = None


def get_convergence_starter():
    """Return global :obj:`ConvergenceStarter` service"""
    return _convergence_starter


def set_convergence_starter(convergence_starter):
    """Set global :obj:`ConvergenceStarter` service"""
    global _convergence_starter
    _convergence_starter = convergence_starter
