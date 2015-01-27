"""Converger service"""

from effect.twisted import perform

from twisted.application.service import Service

from otter.constants import LOCK_PATH
from otter.convergence.composition import (
    execute_convergence, get_desired_group_state)
from otter.util.deferredutils import with_lock


class Converger(Service, object):
    """Converger service"""

    def __init__(self, reactor, kz_client, store, dispatcher):
        self._reactor = reactor
        self._kz_client = kz_client
        self._store = store
        self._dispatcher = self.dispatcher

    def _get_lock(self, group_id):
        """Get a ZooKeeper-backed lock for converging the group."""
        path = '{}/convergence/{}'.format(LOCK_PATH, group_id)
        return self._kz_client.Lock(path)

    def converge(self, group_id, desired, launch_config):
        """Converge a group to a capacity with a launch config."""
        desired_group_state = get_desired_group_state(
            group_id, launch_config, desired)

        def exec_convergence():
            eff = execute_convergence(group_id, desired_group_state,
                                      launch_config)
            return perform(self._dispatcher, eff)
        return with_lock(
            self._reactor, self._get_lock(group_id), exec_convergence,
            acquire_timeout=150, release_timeout=150)


# Global converger service
# We're using a global now because it's difficult to thread a new parameter
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
