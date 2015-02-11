"""Converger service"""

import time

from functools import partial

from effect import Effect
from effect.do import do
from effect.twisted import perform

from twisted.application.service import Service

from otter.constants import CONVERGENCE_LOCK_PATH
from otter.convergence.composition import get_desired_group_state
from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.planning import plan
from otter.http import TenantScope
from otter.models.intents import ModifyGroupState
from otter.util.deferredutils import with_lock
from otter.util.fp import obj_assoc


def server_to_json(server):
    return {'id': server.id}


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

    @do
    def _converge_eff(self, scaling_group, group_state, launch_config,
                      now, log):
        servers, lb_nodes = yield get_all_convergence_data(
            group_state.group_id)
        desired_group_state = get_desired_group_state(
            group_state.group_id, launch_config, group_state.desired)
        steps, active, num_pending = plan(desired_group_state, servers,
                                          lb_nodes, now)
        active = {server.id: server_to_json(server) for server in active}
        pending = {job_id: {'convergence-job': True}
                   for job_id in range(num_pending)}
        log.msg(otter_event_type='convergence-active-pending',
                active=active,
                pending=pending)
        new_state = obj_assoc(group_state, active=active, pending=pending)
        yield Effect(ModifyGroupState(scaling_group=scaling_group,
                                      group_state=new_state))
        steps_eff = steps_to_effect(steps)
        yield steps_eff

    def start_convergence(self, log, scaling_group, group_state,
                          launch_config,
                          perform=perform):
        """Converge a group to a capacity with a launch config."""
        def exec_convergence():
            log.msg(otter_event_type='convergence-rocks')
            eff = self._converge_eff(scaling_group, group_state, launch_config,
                                     time.time(), log)
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
