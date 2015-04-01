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
from otter.models.intents import GetScalingGroupInfo, ModifyGroupState
from otter.models.interface import NoSuchScalingGroupError
from otter.util.fp import assoc_obj
from otter.util.zk import CreateOrSet, DeleteNode, GetChildrenWithStats


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

    :return: An Effect of a list containing the individual step results.
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

    if worst_status == StepResult.SUCCESS:
        # Do one last gathering + writing to `active` so we get updated
        # based on any DELETEs or other stuff that happened.
        (servers, lb_nodes) = yield gather_eff
        active = determine_active(servers, lb_nodes)
        yield _update_active(scaling_group, active)
        # given that we're gathering in this case, wouldn't it make sense to
        # also plan, and then to execute that plan if something is found...?

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
        error=lambda e: log.err(exc_info_to_failure(e), 'mark-clean-failure'))


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


def make_lock_set():
    """
    Create a multi-lock function, which is a function that takes a key and an
    effect, and runs the effect as long as no other multi-locked effect for the
    same key is being run.

    :return: a callable of (key, Effect) -> Effect, where the result of the
        returned Effect will be the given effect's result, or an error of
        :obj:`ConcurrentError` if the given key already has an effect being
        performed by the same multi-lock function.
    """
    return partial(non_concurrently, Reference(pset()))


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


def get_my_divergent_groups(my_buckets, all_buckets):
    """
    Look up groups that are divergent and that are this node's
    responsibility, according to ``my_buckets``.

    :param my_buckets: collection of buckets allocated to this node
    :param all_buckets: collection of all buckets

    :returns: list of dicts, where each dict has ``tenant_id``,
        ``group_id``, and ``version`` keys.
    """
    def structure_info(x):
        # Names of the dirty flags are {tenant_id}_{group_id}.
        path, stat = x
        tenant, group = parse_dirty_flag(x[0])
        return {'tenant_id': tenant, 'group_id': group,
                'version': stat.version}

    def got_children_with_stats(children_with_stats):
        dirty_info = map(structure_info, children_with_stats)
        num_buckets = len(all_buckets)
        converging = (
            info for info in dirty_info
            if _stable_hash(info['tenant_id']) % num_buckets in my_buckets)
        return list(converging)

    # This is inefficient since we're getting stat information about nodes that
    # we don't necessarily care about, but this is convenient for now.
    eff = Effect(GetChildrenWithStats(CONVERGENCE_DIRTY_DIR))
    return eff.on(got_children_with_stats)


@do
def converge_one_group(log, group_locks, tenant_id, group_id, version,
                       execute_convergence=execute_convergence):
    """
    Converge one group, non-concurrently, and clean up the dirty flag when
    done.

    :param group_locks: A lock function, produced from :func:`make_lock_set`.
    :param version: version number of ZNode of the group's dirty flag
    """
    log = log.bind(tenant_id=tenant_id, group_id=group_id)
    eff = execute_convergence(tenant_id, group_id, log)
    try:
        result = yield group_locks(group_id, eff)
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
def converge_all_groups(log, group_locks, my_buckets, all_buckets,
                        get_my_divergent_groups=get_my_divergent_groups,
                        converge_one_group=converge_one_group):
    """
    Check for groups that need convergence and which match up to the
    buckets we've been allocated.
    """
    # TODO: If we find that there's a group in `group_locks` that's *not* found
    # in the divergent list in ZK, we should stop retrying convergence for that
    # group.  This gives us a mechanism to stop convergence manually when it's
    # spiraling out of control.
    # https://github.com/rackerlabs/otter/issues/1215
    group_infos = yield get_my_divergent_groups(my_buckets, all_buckets)
    if not group_infos:
        return
    log.msg('converge-all-groups', group_infos=group_infos)
    # TODO: Log currently converging
    # https://github.com/rackerlabs/otter/issues/1216
    effs = [
        Effect(TenantScope(
            converge_one_group(log, group_locks,
                               info['tenant_id'],
                               info['group_id'],
                               info['version']),
            info['tenant_id']))
        for info in group_infos]
    yield do_return(parallel(effs))


def _stable_hash(s):
    """Get a stable hash of a string as an integer."""
    # :func:`hash` is not stable with different pythons/architectures.
    return int(sha1(s).hexdigest(), 16)


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
        self.log = log.bind(system='converger')
        self.partitioner = partitioner_factory(self.log, self.buckets_acquired)
        self.partitioner.setServiceParent(self)
        self.group_locks = make_lock_set()
        self._converge_all_groups = converge_all_groups

    def buckets_acquired(self, my_buckets):
        """
        Perform the effectful result of :func:`check_convergence`.

        This is used as the partitioner callback.
        """
        eff = self._converge_all_groups(self.log, self.group_locks,
                                        my_buckets, self._buckets)
        result = perform(self._dispatcher, eff).addErrback(
            self.log.err, 'converge-all-groups-error')
        # the return value is ignored, but we return this for testing
        return result

    def divergent_changed(self, children):
        self.log.msg('convergence-zk-watch')
        if self.partitioner.partitioner.acquired:
            # TODO: don't use private stuff :(
            # TODO: only call buckets_acquired if we own some of the children
            # TODO: maybe don't do so much work?
            # TODO: nagle?
            my_buckets = self.partitioner._get_current_buckets()
            self.buckets_acquired(my_buckets)

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
