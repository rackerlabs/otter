"""Converger service"""

import time

from effect import Effect, FirstError, Func, catch, parallel
from effect.do import do, do_return
from effect.twisted import exc_info_to_failure, perform

from pyrsistent import pset

import six

from toolz.itertoolz import concat

from twisted.application.service import MultiService, Service

from otter.constants import CONVERGENCE_DIRTY_DIR, CONVERGENCE_DIRTY_PATH
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.model import ServerState
from otter.convergence.planning import plan
from otter.http import TenantScope
from otter.models.intents import GetScalingGroupInfo, ModifyGroupState
from otter.models.interface import NoSuchScalingGroupError
from otter.util.fp import ERef, assoc_obj
from otter.util.zk import CreateOrSet, DeleteNode, GetChildrenWithStats


def server_to_json(server):
    """
    Convert a NovaServer to a dict representation suitable for returning to the
    end-user as a part of group state.
    """
    return {'id': server.id}


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
        desired_lbs = set(concat(server.desired_lbs.values()))
        met_desireds = set([
            desired for desired in desired_lbs
            for node in current_lb_nodes
            if desired.equivalent_definition(node.description)])
        return desired_lbs == met_desireds

    return [s for s in servers
            if s.state == ServerState.ACTIVE
            and all_met(s, [node for node in lb_nodes if node.matches(s)])]


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


def execute_convergence(tenant_id, group_id, log,
                        get_all_convergence_data=get_all_convergence_data):
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
    log.msg("execute-convergence")
    # Huh! It turns out we can parallelize the gathering of data with the
    # fetching of the scaling group info from cassandra.
    sg_eff = Effect(GetScalingGroupInfo(tenant_id=tenant_id,
                                        group_id=group_id))
    gather_eff = get_all_convergence_data(group_id)

    def got_all_data(((scaling_group, group_state, launch_config),
                      (servers, lb_nodes))):
        time_eff = Effect(Func(time.time))

        def got_time(now):
            desired_group_state = get_desired_group_state(
                group_id, launch_config, group_state.desired)
            steps = plan(desired_group_state, servers, lb_nodes, now)
            active = determine_active(servers, lb_nodes)
            log.msg("convergence-plan",
                    servers=servers, lb_nodes=lb_nodes, steps=steps, now=now,
                    desired=desired_group_state, active=active)
            eff = _update_active(scaling_group, active)
            eff = eff.on(lambda _: steps_to_effect(steps))
            return eff
        return time_eff.on(got_time)

    return Effect(TenantScope(
        parallel([sg_eff, gather_eff]).on(
            success=got_all_data,
            error=catch(FirstError, lambda fe: six.reraise(*fe[1].exc_info))),
        tenant_id
    ))


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

    # So instead of just a boolean flag, we'll takie advantage of ZK node
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

    path = CONVERGENCE_DIRTY_PATH.format(tenant_id=tenant_id,
                                         group_id=group_id)
    eff = Effect(CreateOrSet(path=path, content='dirty'))
    return eff


class ConvergenceStarter(Service, object):
    """
    A service that allows registering interest in convergence, but does not
    actually execute convergence (see :obj:`Converger` for that).
    """
    def __init__(self, dispatcher):
        self._dispatcher = dispatcher

    def start_convergence(self, log, tenant_id, group_id, perform=perform):
        """Record that a group needs converged."""
        log = log.bind(tenant_id=tenant_id, group_id=group_id)
        log.msg("Marking group dirty", 'mark-dirty')
        eff = mark_divergent(tenant_id, group_id)
        d = perform(self._dispatcher, eff)
        d.addErrback(log.err, 'mark-dirty-failed')
        return d


def _is_fatal(exception):
    """
    Determine if an exception is fatal -- and should consider the group wedged
    so we don't try to converge again.

    Unknown errors are non-fatal, which mean that convergence should be
    retried.
    """
    if type(exception) is NoSuchScalingGroupError:
        return True
    else:
        return False


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

    def __init__(self, log, dispatcher, buckets, partitioner_factory):
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
        self.currently_converging = ERef(pset())

    def buckets_acquired(self, my_buckets, perform=perform):
        """
        Perform the effectful result of :func:`check_convergence`.

        This is used as the partitioner callback.
        """
        self.log.msg("buckets-acquired", my_buckets=my_buckets)
        eff = self.converge_all(my_buckets)
        return perform(self._dispatcher, eff).addErrback(
            self.log.err, "converge-all-error")

    def get_my_divergent_groups(self, my_buckets):
        """
        Look up groups that are divergent and that are this node's
        responsibility, according to the ``self.buckets``.

        :returns: list of dicts, where each dict has ``tenant_id``,
            ``group_id``, and ``version`` keys.
        """
        def structure_info(x):
            # Names of the dirty flags are {tenant_id}_{group_id}.
            path, stat = x
            tenant, group = x[0].split('_', 1)
            return {'tenant_id': tenant, 'group_id': group,
                    'version': stat.version}

        def got_children_with_stats(children_with_stats):
            dirty_info = map(structure_info, children_with_stats)
            converging = (
                info for info in dirty_info
                if hash(info['tenant_id']) % len(self._buckets) in my_buckets)
            return list(converging)

        eff = Effect(GetChildrenWithStats(CONVERGENCE_DIRTY_DIR))
        return eff.on(got_children_with_stats)

    @do
    def converge_all(self, my_buckets):
        """
        Check for groups that need convergence and which match up to the
        buckets we've been allocated.
        """
        group_infos = yield self.get_my_divergent_groups(my_buckets)
        self.log.msg("converge-all", group_infos=group_infos)
        effs = [
            self.converge_one_then_cleanup(
                info['tenant_id'], info['group_id'], info['version'])
            for info in group_infos]
        yield do_return(parallel(effs))

    @do
    def converge_one_then_cleanup(self, tenant_id, group_id, version):
        """
        Converge one group, and clean up the dirty flag after we're done.

        :param version: The version number associated with the dirty flag at
            the time we read it. The dirty flag will only be cleaned up if the
            version number doesn't change.
        """
        log = self.log.bind(tenant_id=tenant_id, group_id=group_id)
        try:
            yield self.converge_one_non_concurrently(tenant_id, group_id, log)
        except Exception as e:
            if _is_fatal(e):
                yield self._cleanup(log, tenant_id, group_id, version)
                # TODO: change group state to ERROR.
                raise
            else:
                log.err(None, "converge-non-fatal-error")
        else:
            yield self._cleanup(log, tenant_id, group_id, version)

    @do
    def converge_one_non_concurrently(self, tenant_id, group_id, log,
                                      execute_convergence=execute_convergence):
        """Converge one group if we're not already converging it."""
        # Even though we yield for ERef access/modification, we can rely on it
        # being synchronous, so no worries about race conditions for this
        # conditional and the following addition of the group:
        if group_id in (yield self.currently_converging.read()):
            log.msg("already-converging")
            return
        yield self.currently_converging.modify(lambda cc: cc.add(group_id))
        # However, the convergence itself is asynchronous.  Can we have a race
        # condition here?  In fact, won't this have the same problem that we
        # have with the `dirty` flag? Kind of, but it doesn't matter. It's
        # possible that another call to maybe_converge_one will happen to this
        # same group just after this converge_one call, and before we remove
        # the group from currently_converging. But it doesn't matter! Because
        # the surrounding dirty-checking, with its version-numbered flag, will
        # keep the group in the "divergent" state no matter what. :-)
        try:
            result = yield execute_convergence(tenant_id, group_id, log)
        finally:
            yield self.currently_converging.modify(
                lambda cc: cc.remove(group_id))
        yield do_return(result)

    def _cleanup(self, log, tenant_id, group_id, version):
        """
        Delete the dirty flag, if its version hasn't changed. See comment in
        :func:`start_convergence_eff` for more info.

        :return: Effect of None.
        """
        log.msg("convergence-mark-clean")
        path = CONVERGENCE_DIRTY_PATH.format(tenant_id=tenant_id,
                                             group_id=group_id)
        return Effect(DeleteNode(path=path, version=version)).on(
            error=lambda e: log.err(exc_info_to_failure(e),
                                    'mark-clean-failed'))

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
