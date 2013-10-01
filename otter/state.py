"""
Contains code to handle group changes from nova.
"""

from otter.controller import execute_group_transition
from otter.util.hashkey import generate_transaction_id


class GroupEvent(object):
    """
    A change in the group
    """

    ADDED, DELETING, DELETED, ERROR, ACTIVE = range(1, 6)

    def __init__(self, tenant_id, group_id, server_id, change):
        """
        :param group_id: Group ID
        :param server_id: Server ID of server that changed
        :param change: One of the above ADDED, DELETING...
        """
        self.tenant_id = tenant_id
        self.group = group
        self.server_id = server_id
        self.change = change


_group_transitions = {
    GroupEvent.ADDED: server_created,
    GroupEvent.DELETING: server_deleting,
    GroupEvent.DELETED: server_deleted,
    GroupEvent.ERROR: server_error,
    GroupEvent.ACTIVE: server_active
}


class GroupEventReceiver(object):
    """
    Receive `GroupEvent` events from Atom hopper
    """
    def __init__(self, store):
        self.store = store

    def group_event_received(event):
        """
        Called when `GroupEvent` is received from AtomHopper
        """
        log = log.bind(event_run_id=generate_transaction_id())
        group = self.store.get_scaling_group(log, event.tenant_id, event.group_id)
        d = group.modify_state(self.process_group_event, event)
        d.addErrback(log.err)

    def process_group_event(self, group, state, event):
        """
        Process group event
        """
        # call any of below server change events
        changed_state = _group_transitions[event.change](
            log.bind(server_id=event.server_id), group, state, event.server_id))
        # and execute state transition
        return changed_state and execute_group_transition(log, group, changed_state) or state


def remove_server(state, server_id):
    """
    Remove server from state
    """
    if server_id in state.active:
        info = state.remove_active(server_id)
    elif server_id in state.pending:
        info = state.remove_pending(server_id)
    elif server_id in state.error:
        info = state.remove_error(server_id)
    elif server_id in state.deleting:
        info = state.remove_deleting(server_id)
    elif server_id in state.deleted:
        info = state.remove_deleted(server_id)
    else:
        raise ValueError('Unknown server_id')
    return info


def server_created(log, group, state, server_id):
    """
    Called when server `server_id` is added to `group`. It just got created.
    """
    if server_id not in state.pending:
        log.msg('Untracked server created', server_id=server_id)
    return None


def server_deleted(log, group, state, server_id):
    """
    Called when `server_id` server is deleted from `group`
    """
    try:
        info = remove_server(state, server_id)
        state.add_deleted(server_id, info)
        return state
    except ValueError:
        # ERROR. A server we did not track got deleted
        log.msg('Untracked server deleted')


def server_deleting(log, group, state, server_id):
    """
    Called when a server `server_id` has started deleting
    """
    try:
        server_info = remove_server(state, server_id)
        state.add_deleting(server_info)
        return state
    except ValueError:
        # ERROR. A server we did not track started deleting
        log.msg('Untracked server started deleting')


def server_active(log, group, state, server_id):
    """
    Called when `server_id` server has finished building
    """
    if server_id in state.active:
        # Already active. Do nothing
        return None
    try:
        server_info = remove_server(state, server_id)
        state.add_active(server_id, server_info)
        return state
    except ValueError:
        # ERROR. A server we did not track started deleting
        log.msg('Untracked server became active')


def server_error(log, group, state, server_id):
    """
    Called when `server_id` server went to error state
    """
    try:
        info = remove_server(state, server_id)
        state.add_error(server_id, info)
        return state
    except ValueError:
        # ERROR: unknown server got deleted
        log.msg('Untracked server errored')


def check_state_after(group, server_id, server_state, timeout):
    """
    Check that state of given server `server_id` is `server_state` after timeout
    """
    pass


def remove_scheduled_check(group, server_id):
    """
    Remove scheduled state check for `server_id`
    """
    pass


