"""Converger service"""

import time

from functools import partial

from effect import Effect
from effect.twisted import perform

from toolz.itertoolz import concat

from twisted.application.service import MultiService, Service

from otter.constants import CONVERGENCE_DIRTY_PATH
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.model import ServerState
from otter.convergence.planning import plan
from otter.http import TenantScope
from otter.models.intents import ModifyGroupState
from otter.util.deferredutils import with_lock
from otter.util.fp import assoc_obj
from otter.util.zk import create_or_update


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


    def _mark_dirty(self, group_id):
        # This is trickier than just "create a znode; ignore a
        # NodeExistsError", because that will allow a race condition that can
        # lead to stalled convergence. Here's the scenario, with Otter nodes
        # 'A' and 'B'.

        # - A: mark group N dirty
        # -               B: converge group N (repeat until done)
        # - A: mark group N dirty, ignore NodeExistsError
        # -               B: mark group N clean

        # Here, a policy was executed on group N twice, and A tried to mark it
        # dirty twice, but failed the second time because the group was already
        # marked dirty. The problem is that when the converger node finished
        # converging based on the first time it noticed the group was dirty, it
        # then marked it clean *after* node A tried to mark it dirty a second
        # time. Usually this will not be a problem because at the beginning of
        # each iteration of convergence, the desired group state will be
        # recalculated, so as long as the "duplicate" dirty happens before the
        # final iteration, nothing will be lost. But if it happens at just the
        # right moment, after the final iteration and before the group is
        # marked clean, then we will be stalled.

        # The way we solve this is by storing a counter in the node, using a
        # strong version-based check-and-set. Every time we mark dirty, we
        # either create the dirty-flag zknode with '1' as the content, or if
        # the dirty-flag zknode already exists, it will be incremented. Then,
        # when convergence finishes, instead of deleting the zknode outright,
        # it will decrement it if the value is >1 and delete it if it is 1
        # (again, with a strong version-based check-and-set).

        path = CONVERGENCE_DIRTY_PATH.format(group_id=group_id)
        d = create_or_update(self._kz_client,
                             path,
                             lambda x: str(int(x) + 1),
                             '1')
        d.addErrback(log.err, otter_msg_type='mark-dirty-failed')
        return d

    def start_convergence(self, log, group_id):
        """
        Indicate that a group should be converged.

        This doesn't actually do the work of convergence, it effectively just
        puts an item in a queue.

        :param log: a bound logger.
        :param group_id: The ID of the group to converge.
        """
        log.msg("Marking group dirty",
                otter_msg_type='convergence-mark-dirty')
        self._mark_dirty(group_id)


class Converger(MultiService, object):
    """
    A service that searches for groups that need converging and then does the
    work of converging them.

    Work is split up between nodes running this service by using a Kazoo
    :obj:`SetPartitioner`. This service could be run separately from the API
    nodes.
    """

    def __init__(self, log, kz_client, store, dispatcher, num_buckets,
                 partitioner_factory):
        """
        :param log: a bound log
        :param kz_client: txKazoo client
        :param store: cassandra store
        """
        self._kz_client = kz_client
        self._dispatcher = dispatcher
        self._num_buckets = num_buckets
        self.log = log.bind(system='converger')
        self.partitioner = partitioner_factory(
            self.log, self._check_convergence)

    def _check_convergence(self, buckets):
        """
        Check for groups that need convergence and which match up to the
        buckets we've been allocated.
        """
        # list everything in CONVERGENCE_DIRTY_PATH
        # if hash(el) % self.num_buckets in buckets: CONVERGE IT!

    def exec_convergence(self, log, scaling_group, group_state,
                         launch_config,
                         perform=perform,
                         execute_convergence=execute_convergence):
        """
        Converge a group to a capacity with a launch config.

        :param log: a bound logger.
        :param IScalingGroup scaling_group: The scaling group object.
        :param GroupState group_state: The group state.
        :param launch_config: An otter launch config.
        :param perform: :func:`perform` function to use for testing.
        :param execute_convergence: :func:`execute_convergence` function to use
            for testing.
        """
        eff = execute_convergence(scaling_group, group_state.desired,
                                  launch_config, time.time(), log)
        eff = Effect(TenantScope(eff, group_state.tenant_id))
        d = perform(self._dispatcher, eff)
        return d.addErrback(log.err, "Error when performing convergence",
                            otter_msg_type='convergence-perform-error')


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
