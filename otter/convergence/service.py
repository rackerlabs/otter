"""
Converger service

The top-level entry-points into this module are :obj:`ConvergenceStarter` and
:obj:`Converger`.
"""

import time
from functools import partial
from hashlib import sha1

from effect import Effect, FirstError, Func, parallel
from effect.do import do, do_return
from effect.ref import Reference
from effect.twisted import exc_info_to_failure, perform

from kazoo.recipe.partitioner import PartitionState

from pyrsistent import pset
from pyrsistent import thaw

import six

from twisted.application.service import MultiService

from otter.cloud_client import TenantScope
from otter.constants import CONVERGENCE_DIRTY_DIR
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.model import ServerState, StepResult
from otter.convergence.planning import plan
from otter.models.intents import (
    DeleteGroup, GetScalingGroupInfo, ModifyGroupState)
from otter.models.interface import NoSuchScalingGroupError, ScalingGroupStatus
from otter.util.fp import assoc_obj
from otter.util.zk import CreateOrSet, DeleteNode, GetChildren, GetStat


def server_to_json(server):
    """
    Convert a NovaServer to a dict representation suitable for returning to the
    end-user as a part of group state.
    """
    return {'id': server.id, 'links': thaw(server.links)}


def determine_active(servers, lb_nodes):
    """
    Given the current NovaServers and LB nodes, determine which servers are
    completely built.

    :param servers: sequence of :obj:`NovaServer`.
    :param lb_nodes: sequence of :obj:`ILBNode`.

    :return: list of servers that are active.
    """

    def all_met(server, current_lb_nodes):
        """Determine if a server is in all the LBs it wants to be in."""
        desired_lbs = server.desired_lbs
        met_desireds = set([
            desired for desired in desired_lbs
            for node in current_lb_nodes
            if desired.equivalent_definition(node.description)])
        return desired_lbs == met_desireds

    return [s for s in servers
            if (s.state == ServerState.ACTIVE and
                all_met(s, [node for node in lb_nodes if node.matches(s)]))]


def _update_active(scaling_group, active):
    """
    :param scaling_group: scaling group
    :param active: list of active NovaServer objects
    """
    active = {server.id: server_to_json(server) for server in active}

    def update_group_state(group, old_state):
        return assoc_obj(old_state, active=active)

    return Effect(ModifyGroupState(scaling_group=scaling_group,
                                   modifier=update_group_state))


@do
def execute_convergence(tenant_id, group_id, log,
                        get_all_convergence_data=get_all_convergence_data,
                        plan=plan):
    """
    Gather data, plan a convergence, save active and pending servers to the
    group state, and then execute the convergence.

    :param group_id: group id
    :param log: bound logger
    :param get_all_convergence_data: like :func`get_all_convergence_data`, used
        for testing.

    :return: Effect of most severe StepResult
    :raise: :obj:`NoSuchScalingGroupError` if the group doesn't exist.
    """
    # Huh! It turns out we can parallelize the gathering of data with the
    # fetching of the scaling group info from cassandra.
    sg_eff = Effect(GetScalingGroupInfo(tenant_id=tenant_id,
                                        group_id=group_id))
    gather_eff = get_all_convergence_data(group_id)
    try:
        data = yield parallel([sg_eff, gather_eff])
    except FirstError as fe:
        six.reraise(*fe.exc_info)
    [(scaling_group, manifest), (servers, lb_nodes)] = data

    group_state = manifest['state']
    launch_config = manifest['launchConfiguration']
    now = yield Effect(Func(time.time))

    group_status = ScalingGroupStatus.lookupByName(manifest['status'])
    if group_status == ScalingGroupStatus.DELETING:
        group_state.desired = 0

    desired_group_state = get_desired_group_state(
        group_id, launch_config, group_state.desired)
    steps = plan(desired_group_state, servers, lb_nodes, now)
    active = determine_active(servers, lb_nodes)
    log.msg('execute-convergence',
            servers=servers, lb_nodes=lb_nodes, steps=steps, now=now,
            desired=desired_group_state, active=active)
    yield _update_active(scaling_group, active)
    if len(steps) == 0:
        yield do_return(StepResult.SUCCESS)
    results = yield steps_to_effect(steps)

    severity = [StepResult.FAILURE, StepResult.RETRY, StepResult.SUCCESS]
    priority = sorted(results,
                      key=lambda (status, reasons): severity.index(status))
    worst_status = priority[0][0]
    log.msg('execute-convergence-results',
            results=zip(steps, results),
            worst_status=worst_status)

    if (worst_status == StepResult.SUCCESS and
            group_status == ScalingGroupStatus.DELETING):
            # servers have been deleted. Delete the group for real
        yield Effect(DeleteGroup(tenant_id=tenant_id, group_id=group_id))

    yield do_return(worst_status)


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


def delete_divergent_flag(log, tenant_id, group_id, version):
    """
    Delete the dirty flag, if its version hasn't changed. See comment in
    :func:`mark_divergent` for more info.

    :return: Effect of None.
    """
    flag = format_dirty_flag(tenant_id, group_id)
    path = CONVERGENCE_DIRTY_DIR + '/' + flag
    return Effect(DeleteNode(path=path, version=version)).on(
        success=lambda r: log.msg('mark-clean-success'),
        error=lambda e: log.err(exc_info_to_failure(e), 'mark-clean-failure',
                                path=path, dirty_version=version))


class ConvergenceStarter(object):
    """
    A service that allows indicating that a group has diverged and needs
    convergence, but does not do the converging itself (see :obj:`Converger`
    for that).
    """
    def __init__(self, dispatcher):
        self._dispatcher = dispatcher

    def start_convergence(self, log, tenant_id, group_id, perform=perform):
        """Record that a group needs converged by creating a ZooKeeper node."""
        log = log.bind(tenant_id=tenant_id, group_id=group_id)
        eff = mark_divergent(tenant_id, group_id)
        d = perform(self._dispatcher, eff)

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

    :param log: bound log
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
def converge_one_group(log, currently_converging, tenant_id, group_id, version,
                       execute_convergence=execute_convergence):
    """
    Converge one group, non-concurrently, and clean up the dirty flag when
    done.

    :param Reference currently_converging: pset of currently converging groups
    :param version: version number of ZNode of the group's dirty flag
    """
    log = log.bind(tenant_id=tenant_id, group_id=group_id)
    eff = execute_convergence(tenant_id, group_id, log)
    try:
        result = yield non_concurrently(currently_converging, group_id, eff)
    except ConcurrentError:
        # We don't need to spam the logs about this, it's to be expected
        return
    except NoSuchScalingGroupError:
        log.err(None, 'converge-fatal-error')
        yield delete_divergent_flag(log, tenant_id, group_id, version)
        return
    except Exception:
        # We specifically don't clean up the dirty flag in the case of
        # unexpected errors, so convergence will be retried.
        log.err(None, 'converge-non-fatal-error')
    else:
        if result in (StepResult.FAILURE, StepResult.SUCCESS):
            yield delete_divergent_flag(log, tenant_id, group_id, version)
        # TODO: if result is FAILURE, put the group into ERROR state.
        # https://github.com/rackerlabs/otter/issues/885


@do
def converge_all_groups(log, currently_converging, my_buckets, all_buckets,
                        divergent_flags,
                        converge_one_group=converge_one_group):
    """
    Check for groups that need convergence and which match up to the
    buckets we've been allocated.
    """
    group_infos = get_my_divergent_groups(
        my_buckets, all_buckets, divergent_flags)
    # filter out currently converging groups
    cc = yield currently_converging.read()
    group_infos = [info for info in group_infos if info['group_id'] not in cc]
    if not group_infos:
        return
    log.msg('converge-all-groups', group_infos=group_infos,
            currently_converging=list(cc))

    effs = [
        Effect(GetStat(info['dirty-flag'])).on(
            lambda stat, info=info: Effect(TenantScope(
                converge_one_group(log, currently_converging,
                                   info['tenant_id'],
                                   info['group_id'],
                                   stat.version),
                info['tenant_id'])))
        for info in group_infos]
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

    def __init__(self, log, dispatcher, buckets, partitioner_factory,
                 converge_all_groups=converge_all_groups):
        """
        :param log: a bound log
        :param dispatcher: The dispatcher to use to perform effects.
        :param buckets: collection of logical `buckets` which are shared
            between all Otter nodes running this service. Will be partitioned
            up between nodes to detirmine which nodes should work on which
            groups.
        :param partitioner_factory: Callable of (log, callback) which should
            create an :obj:`Partitioner` to distribute the buckets.
        """
        MultiService.__init__(self)
        self._dispatcher = dispatcher
        self._buckets = buckets
        self.log = log.bind(otter_service='converger')
        self.partitioner = partitioner_factory(self.log, self.buckets_acquired)
        self.partitioner.setServiceParent(self)
        self.currently_converging = Reference(pset())
        self._converge_all_groups = converge_all_groups

    def _converge_all(self, my_buckets, divergent_flags):
        """Run :func:`converge_all_groups` and log errors."""
        eff = self._converge_all_groups(self.log, self.currently_converging,
                                        my_buckets, self._buckets,
                                        divergent_flags)
        return eff.on(
            error=lambda e: self.log.err(
                exc_info_to_failure(e), 'converge-all-groups-error'))

    def buckets_acquired(self, my_buckets):
        """
        Get dirty flags from zookeeper and run convergence with them.

        This is used as the partitioner callback.
        """
        eff = Effect(GetChildren(CONVERGENCE_DIRTY_DIR)).on(
            partial(self._converge_all, my_buckets))
        return perform(self._dispatcher, eff)

    def divergent_changed(self, children):
        """
        ZooKeeper children-watch callback that lets this service know when the
        divergent groups have changed. If any of the divergent flags are for
        tenants associated with this service's buckets, a convergence will be
        triggered.
        """
        my_buckets = self.partitioner.get_current_buckets()
        changed_buckets = set(
            bucket_of_tenant(parse_dirty_flag(child)[0], len(self._buckets))
            for child in children)
        if (self.partitioner.get_current_state() == PartitionState.ACQUIRED and
                set(my_buckets).intersection(changed_buckets)):
            # the return value is ignored, but we return this for testing
            eff = self._converge_all(my_buckets, children)
            return perform(self._dispatcher, eff)

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
