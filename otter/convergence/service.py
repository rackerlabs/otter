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
        # TODO: There's a race condition here that will still lead to
        # convergence stalling, in rare conditions.

        # - A: mark group N dirty due to policy
        # -               B: converge group N (repeat until done)
        # - A: mark group N dirty due to policy, get a NodeExistsError
        # -               B: mark group N clean

        # Basically, if a policy is executed just as the final convergence
        # iteration is completing, and the group is marked dirty just before
        # the converging node marks it clean, the change from the policy won't
        # immediately take effect (though if another event happens later it
        # should be resolved).

        # How do we solve this?

        # a. Store a counter in the node. Not sure if this can be done
        #    reliably. Each mark_dirty would increment it, each no-op
        #    convergence would decrement it. I don't think we need to care
        #    beyond 2, but I'm not sure.
        # b. Investigate using the ZK "queue" pattern to do the same general
        #    idea as in `a`.
        # c. After marking a group clean, check to see if desired has changed
        #    as a last-ditch check to see if we need to run convergence again.
        return self._kz_client.create(
            CONVERGENCE_DIRTY_PATH.format(group_id=group_id),
            makepath=True
        ).addErrback(
            log.err, "Failed to mark dirty",
            otter_msg_type="convergence-mark-dirty-error"
        )

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

    def __init__(self, log, kz_client, store, dispatcher, partitioner_factory):
        """
        :param log: a bound log
        :param kz_client: txKazoo client
        :param store: cassandra store
        """
        self._kz_client = kz_client
        self._dispatcher = dispatcher
        self._timer = TimerService(interval, self.check_convergence)
        self._timer.setServiceParent(self)
        self._num_buckets = num_buckets
        self.log = log.bind(system='converger')
        self.partitioner = partitioner_factory(self.log, self.check_convergence)

    def startService(self):
        super(Converger, self).startService()

    def check_convergence(self):
        """
        Check for events occurring now and earlier
        """
        utcnow = datetime.utcnow()
        log = self.log.bind(scheduler_run_id=generate_transaction_id(), utcnow=utcnow)
        # TODO: This log might feel like spam since it'll occur on every tick. But
        # it'll be useful to debug partitioning problems (at least in initial deployment)
        log.msg('Got buckets {buckets}', buckets=buckets, path=CONVERGENCE_PARTITIONER_PATH)

        return defer.gatherResults(
            [check_events_in_bucket(
                log, self.store, bucket, utcnow, batchsize) for bucket in buckets])

    def start_convergence(self, log, scaling_group, group_state,
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
