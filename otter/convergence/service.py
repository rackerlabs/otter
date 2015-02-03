"""Converger service"""

from functools import partial

from characteristic import attributes

from effect import Effect
from effect.do import do, do_return
from effect.twisted import deferred_performer, perform

from twisted.application.service import Service

from otter.constants import CONVERGENCE_LOCK_PATH
from otter.convergence.composition import (
    execute_convergence, get_desired_group_state)
from otter.convergence.gathering import get_all_convergence_data
from otter.http import TenantScope
from otter.util.deferredutils import with_lock
from otter.util.fp import obj_assoc


@attributes(['scaling_group', 'group_state'])
class ModifyGroupState(object):
    """
    An Effect intent which indicates that a group state should be updated.
    """


@deferred_performer
def perform_modify_group_state(mgs):
    """Perform an :obj:`UpdateGroupState`."""
    return mgs.scaling_group.modify_state(lambda: mgs.state)


def extract_active_and_pending(servers):
    # This is _totally_ wrong. Actives need to be servers that are ACTIVE *and*
    # which have been added to the load balancer, if appropriate.
    # And pendings are servers that haven't yet been added to the LB.
    # (is there a list of states exclusive of pending? like ERROR? Or is it a
    # whitelist of pending states instead?)
    actives = [x for x in servers if x['state'] == 'ACTIVE']
    pendings = [x for x in servers if x['state'] == '???']
    return actives, pendings


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
        servers, lb_nodes = yield get_all_convergence_data(group_state.group_id)
        actives, pendings = extract_active_and_pending(servers)
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
            eff = self._converge_eff(scaling_group, group_state, launch_config, execute_convergence)
            d = perform(self._dispatcher, eff)
            return d.addErrback(log.err, "Error when performing convergence",
                                otter_event_type='convergence-perform-error')
        return with_lock(
            self._reactor, self._get_lock(group_state.group_id), exec_convergence,
            acquire_timeout=150, release_timeout=150)


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
