"""
IGNORE THIS!
Handle group change events by reacting right away. A different implementation than one in state.py
"""


def server_created(group, state, instance_id):
    """
    Called when server `instance_id` is added to `group`. It just got created.
    """
    if instance_id not in state.pending:
        log.msg('Untracked server created', server_id=instance_id)
    return state


def server_deleted(group, state, instance_id):
    """
    Called when `instance_id` server is deleted from `group`
    """
    log = log.bind(server_id=instance_id)
    if instance_id in state.deleting:
        state.remove_deleting(instance_id)
        remove_check(group, instance_id)
    elif instance_id in state.active:
        # active server deleted.
        # remove it from load balancer, create a new server
        remove_from_load_balancers(instance_id)
        state.remove_active(instance_id)
        instance_id = launch_server(group)
        state.add_pending(instance_id)
        # check back the state after 1 hr and see if the server got built
        check_state_after(state, instance_id, ACTIVE, 3600)
    elif instance_id in state.pending:
        # pending server deleted. launch it again
        state.remove_pending(instance_id)
        instance_id = launch_server(group)
        state.add_pending(instance_id)
        check_state_after(state, instance_id, ACTIVE, 3600)
    elif instance_id in state.pending_delete:
        # Got deleted before becoming active. No problem
        log.msg('scheduled deletion got deleted earlier')
    else:
        # ERROR. A server we did not track got deleted
        log.msg('Untracked server deleted')
    return state


def server_active(log, transid, group, state, instance_id):
    """
    Called when `instance_id` server has finished building
    """
    if instance_id in state.pending:
        add_to_load_balancers(instance_id)
        state.move_to_active(instance_id)
    elif instance_id in state.pending_delete:
        # instance scheduled for deletion
        supervisor.delete_server(log, transid, group, instance_id)
        state.remove_pending_delete(instance_id)
        state.add_deleting(instance_id)
    else:
        # Untracked server was building.
        log.msg('Untracked server finished building', server_id=instance_id)
    return state


def server_error(group, state, instance_id):
    """
    Called when `instance_id` server went to error state
    """
    if instance_id in state.active:
        remove_from_load_balancers(instance_id)
        delete_server(instance_id)
        state.remove_active(instance_id)
        new_id = launch_server(group)
        state.add_pending(new_id)
    elif instance_id in state.pending:
        delete_server(instance_id)
        state.remove_pending(instance_id)
        new_id = launch_server(group)
        state.add_pending(new_id)
    elif instance_id in state.deleting:
        # went to error while deleting. Try to delete again
        delete_server(instance_id)
    elif instance_id in state.pending_delete:
        # went to error while building and waiting to delete. Try to delete again
        delete_server(instance_id)
    else:
        # ERROR: unknown server got deleted
        pass
    return state


