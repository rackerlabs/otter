"""Converger service"""

import time

from functools import partial

from effect import Effect
from effect.twisted import perform

from twisted.application.service import Service

from otter.constants import CONVERGENCE_LOCK_PATH
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
        desired_lbs = server.desired_lbs
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


class Converger(Service, object):
    """Converger service"""

    def __init__(self, reactor, kz_client, dispatcher):
        self._reactor = reactor
        self._kz_client = kz_client
        self._dispatcher = dispatcher

    def _get_lock(self, group_id):
        """Get a ZooKeeper-backed lock for converging the group."""
        path = CONVERGENCE_LOCK_PATH.format(group_id=group_id)
        lock = self._kz_client.Lock(path)
        lock.acquire = partial(lock.acquire, timeout=120)
        return lock

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
        def exec_convergence():
            eff = execute_convergence(scaling_group, group_state.desired,
                                      launch_config, time.time(), log)
            eff = Effect(TenantScope(eff, group_state.tenant_id))
            d = perform(self._dispatcher, eff)
            return d.addErrback(log.err, "Error when performing convergence",
                                otter_msg_type='convergence-perform-error')
        return with_lock(
            self._reactor,
            self._get_lock(group_state.group_id),
            exec_convergence,
            acquire_timeout=150,
            release_timeout=150)


# We're using a global for now because it's difficult to thread a new parameter
# all the way through the REST objects to the controller code, where this
# service is used.
_converger = None


def get_converger():
    """Return global converger service"""
    return _converger


def set_converger(converger):
    """Set global converger service"""
    global _converger
    _converger = converger
