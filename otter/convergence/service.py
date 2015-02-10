"""Converger service"""

from functools import partial

from effect import Effect
from effect.do import do, do_return
from effect.twisted import perform

from toolz.itertoolz import concat

from twisted.application.service import Service

from otter.constants import CONVERGENCE_LOCK_PATH
from otter.convergence.composition import (
    execute_convergence, get_desired_group_state)
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.steps import AddNodesToCLB, BulkAddToRCv3, CreateServer
from otter.http import TenantScope
from otter.models.intents import ModifyGroupState
from otter.util.deferredutils import with_lock
from otter.util.fp import obj_assoc


def server_to_json(server):
    return {'id': server.id}


def calculate_active_and_pending(servers, steps):
    """
    Given the current NovaServers and the planned (unthrottled) steps,
    determine which servers are active and which servers are pending.

    :return: Two-tuple of (active, pending) where `active` is a dict of server
    IDs to server info, and `pending` is a dict of arbitrary integers to
    pending server info.
    """
    all_rcv3_server_adds = set(concat([
        [pair[1] for pair in s.lb_node_pairs]
        for s in steps if type(s) is BulkAddToRCv3]))

    all_clb_ips = set(concat([
        [c[0] for c in s.address_configs]
        for s in steps if type(s) is AddNodesToCLB]))

    num_pending = (len(all_rcv3_server_adds)
                   + len(all_clb_ips)
                   + len(s for s in steps if type(s) is CreateServer))

    pending = {job_id: {'convergence-job': True}
               for job_id in range(num_pending)}

    complete = [server for server in servers
                if server.id not in all_rcv3_server_adds
                and server.servicenet_address not in all_clb_ips]
    active = {server.id: server_to_json(server) for server in complete}
    return active, pending


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
                      execute_convergence):
        servers, lb_nodes = yield get_all_convergence_data(
            group_state.group_id)
        actives, pendings = calculate_active_and_pending(servers)
        new_state = obj_assoc(group_state, active=actives, pending=pendings)
        yield Effect(ModifyGroupState(scaling_group=scaling_group,
                                      group_state=new_state))
        desired_group_state = get_desired_group_state(
            group_state.group_id, launch_config, group_state.desired)
        eff = execute_convergence(servers, lb_nodes, group_state.group_id,
                                  desired_group_state)
        result = yield Effect(TenantScope(eff, group_state.tenant_id))
        yield do_return(result)

    def start_convergence(self, log, scaling_group, group_state,
                          launch_config,
                          perform=perform,
                          execute_convergence=execute_convergence):
        """Converge a group to a capacity with a launch config."""
        def exec_convergence():
            eff = self._converge_eff(scaling_group, group_state, launch_config,
                                     execute_convergence)
            d = perform(self._dispatcher, eff)
            return d.addErrback(log.err, "Error when performing convergence",
                                otter_event_type='convergence-perform-error')
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
