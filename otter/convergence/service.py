"""Converger service"""

import time

from effect import Effect
from effect.twisted import perform

from toolz.itertoolz import concat

from twisted.application.service import MultiService, Service
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue

from otter.constants import CONVERGENCE_DIRTY_DIR, CONVERGENCE_DIRTY_PATH
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.model import ServerState
from otter.convergence.planning import plan
from otter.http import TenantScope
from otter.models.intents import ModifyGroupState
from otter.util.fp import assoc_obj
from otter.util.zk import create_or_set, get_children_with_stats


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


def execute_convergence(
        scaling_group, desired_capacity, launch_config, now, log,
        get_all_convergence_data=get_all_convergence_data):
    """
    Gather data, plan a convergence, save active and pending servers to the
    group state, and then execute the convergence.

    :param IScalingGroup scaling_group: The scaling group object.
    :param GroupState group_state: The group state.
    :param launch_config: An otter launch config.
    :param now: The current time in seconds.
    :param log: A bound logger.
    :param get_all_convergence_data: The :func`get_all_convergence_data` to use
        for testing.

    :return: An Effect of a list containing the individual step results.
    """
    all_data_eff = get_all_convergence_data(scaling_group.uuid)

    def got_all_data((servers, lb_nodes)):
        active = determine_active(servers, lb_nodes)
        desired_group_state = get_desired_group_state(
            scaling_group.uuid, launch_config, desired_capacity)
        steps = plan(desired_group_state, servers, lb_nodes, now)
        active = {server.id: server_to_json(server) for server in active}

        def update_group_state(group, old_state):
            return assoc_obj(old_state, active=active)

        eff = Effect(ModifyGroupState(scaling_group=scaling_group,
                                      modifier=update_group_state))
        return eff.on(lambda _: steps_to_effect(steps))

    return all_data_eff.on(got_all_data)


class ConvergenceStarter(Service, object):
    """
    A service that allows registering interest in convergence, but does not
    actually execute convergence (see :obj:`Converger` for that).
    """
    def __init__(self, kz_client):
        self._kz_client = kz_client

    def start_convergence(self, log, tenant_id, group_id):
        """
        Indicate that a group should be converged.

        This doesn't actually do the work of convergence, it effectively just
        puts an item in a queue.

        :param log: a bound logger.
        :param group_id: The ID of the group to converge.
        """
        # This is tricky enough that just using a boolean flag for "is group
        # dirty or not" won't work, because that will allow a race condition
        # that can lead to stalled convergence. Here's the scenario, with Otter
        # nodes 'A' and 'B', assuming only a boolean `dirty` flag:

        # - A: mark group N dirty
        # -               B: converge group N (repeat until done)
        # - A: mark group N dirty, ignore NodeExistsError
        # -               B: mark group N clean

        # Here, a policy was executed on group N twice, and A tried to mark it
        # dirty twice (and ignored a NoNodeError because the fact that it's
        # already there means it's already dirty, so recreating should be a
        # no-op). The problem is that when the converger node finished
        # converging, it then marked it clean *after* node A tried to mark it
        # dirty a second time. Usually this will not be a problem because at
        # the beginning of each iteration of convergence, the desired group
        # state will be recalculated, so as long as the "duplicate" dirty
        # happens before the final iteration, nothing will be lost. But if it
        # happens at just the right moment, after the final iteration and
        # before the group is marked clean, then the changes desired by the
        # second policy execution will not happen.

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

        log.msg("Marking group dirty", otter_msg_type='convergence-mark-dirty')
        path = CONVERGENCE_DIRTY_PATH.format(tenant_id=tenant_id,
                                             group_id=group_id)
        d = create_or_set(self._kz_client, path, 'dirty')
        d.addErrback(log.err, otter_msg_type='mark-dirty-failed')
        return d


class Converger(MultiService):
    """
    A service that searches for groups that need converging and then does the
    work of converging them.

    Work is split up between nodes running this service by using a Kazoo
    :obj:`SetPartitioner`. This service could be run separately from the API
    nodes.

    This service will repeatedly check for groups that need convergence,
    deterministically select the groups to converge based on the partitioned
    buckets, and run convergence on any groups that are not already being
    converged.
    """

    # TODO: A lot more of this could be Effectified. We'd need intents for:
    # - ZK: listing children, deleting nodes, getting stats (exists)
    # - cassandra: getting scaling group and launch config

    def __init__(self, log, kz_client, store, dispatcher, buckets,
                 partitioner_factory):
        """
        :param log: a bound log
        :param kz_client: txKazoo client
        :param IScalingGroupCollection store: scaling group collection
        :param dispatcher: The dispatcher to use to perform effects.
        :param buckets: collection of logical `buckets` which are shared
            between all Otter nodes running this service. Will be partitioned
            up between nodes to detirmine which nodes should work on which
            groups.
        :param partitioner_factory: Callable of (log, callback) which should
            create an :obj:`Partitioner` to distribute the buckets.
        """
        MultiService.__init__(self)
        self._kz_client = kz_client
        self._store = store
        self._dispatcher = dispatcher
        self._buckets = buckets
        self.log = log.bind(system='converger')
        self.partitioner = partitioner_factory(
            self.log, self._check_convergence)
        self.partitioner.setServiceParent(self)
        self._currently_converging = set()

    def _mark_clean(self, tenant_id, group_id, version):
        # See the comment in `ConvergenceStarter._make_dirty` to understand
        # this.
        self._currently_converging.remove(group_id)
        path = CONVERGENCE_DIRTY_PATH.format(tenant_id=tenant_id,
                                             group_id=group_id)
        return self._kz_client.delete(path, version=version)

    def _check_convergence(self, my_buckets):
        """
        Check for groups that need convergence and which match up to the
        buckets we've been allocated.

        This is called occasionally by the Partitioner when buckets have been
        allocated.
        """
        # XXX TODO FIXME RADIX REVIEWERS: what do we do with groups or tenants
        # that are no longer using otter but still have converging flags?
        self.log.msg("checking for any groups needing convergence: {buckets}",
                     buckets=my_buckets)
        def exec_and_cleanup(info):
            d = self.exec_convergence(info['tenant'], info['group'])
            d.addBoth(
                lambda _: self._mark_clean(
                    info['tenant'], info['group'], info['stat'].version))
            return d

        def structure_info(x):
            path, stat = x
            tenant, group = x[0].split('_', 1)
            return {'tenant': tenant, 'group': group, 'stat': stat}

        def got_children_with_stats(children_with_stats):
            self.log.msg("got children with stats: {thing}", thing=children_with_stats)
            # Names of the dirty flags are {tenant_id}_{group_id}.
            dirty_info = map(structure_info, children_with_stats)
            converging = [
                info for info in dirty_info
                if hash(info['tenant']) % len(self._buckets) in my_buckets and
                info['group'] not in self._currently_converging]
            groups = set([info['group'] for info in converging])
            self._currently_converging.update(groups)
            deferreds = map(exec_and_cleanup, converging)
            return gatherResults(deferreds)

        d = get_children_with_stats(self._kz_client, CONVERGENCE_DIRTY_DIR)
        return d.addCallback(got_children_with_stats)

    @inlineCallbacks
    def exec_convergence(self, tenant_id, group_id,
                         perform=perform,
                         execute_convergence=execute_convergence):
        """
        Converge a group to a capacity with a launch config.

        :param group_id: The group which needs converging.
        :param perform: :func:`perform` function to use for testing.
        :param execute_convergence: :func:`execute_convergence` function to use
            for testing.
        """
        scaling_group = self.store.get_scaling_group(self.log,
                                                     tenant_id, group_id)
        group_state = yield scaling_group.view_state()
        launch_config = yield scaling_group.view_launch_config()
        eff = execute_convergence(scaling_group, group_state.desired,
                                  launch_config, time.time(), self.log)
        eff = Effect(TenantScope(eff, group_state.tenant_id))
        result = yield perform(self._dispatcher, eff)
        returnValue(result)


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
