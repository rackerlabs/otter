"""
Contains code to handle state transitions of the group. Will launch/delete server
and update group state to store those transitions
"""

def execute_group_transition(current):
    """
    Compare the current state w.r.t what is desired and execute actions that need
    to be performed to come to desired state
    :return: deferred that fires when all actions are executed
    """
    # TODO: Consider adding to load balancer also

    # TODO: Decide on handling errors from executing nova calls.
    # If overLimit, then pause the group and so on

    # child build and delete times
    d = check_times(current)

    # delete servers in error state
    del_err_deferred = delete_error_servers(current)

    def check_desired(_):
        current_total = len(current.active) + len(current.pending)
        if current_total == current.desired:
            return None
        elif current_total < current.desired:
            return execute_scale_up(current, current.desired - current_total)
        else:
            return execute_scale_down(current, current.desired - current_total)

    return gatherResults([d.addCallback(check_desired), del_err_deferred],
                         consumeErrors=True).addCallback(lambda _: current)


def execute_scale_up(state, delta):
    deferreds = [
        supervisor.launch_server(log, trans_id, group, launch_config)
            .addCallback(lambda s: state.add_pending(s['id'], s))
        for _i in range(delta)
    ]
    return gatherResults(deferreds, consumeErrors=True)


def execute_scale_down(state, delta):

    active_delete_num = delta - len(state.pending)
    if active_delete_num > 0:
        sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
        servers_to_delete = sorted_servers[:delta]
        deferreds =  [supervisor.delete_server(log, trans_id, group, server)
                                .addCallback(partial(state.remove_active, server['id']))
                      for server in servers_to_delete]
        return gatherResults(deferreds, consumeErrors=True)
    else:
        # Cannot delete pending servers now.
        return defer.succeed(None)

def delete_error_servers(log, state):

    def remove_server(_, server_id):
        state.remove_error(server_id)

    deferreds = []
    for server_id in state.error:
        d = delete_server(server_id).addCallback(remove_server, server_id)
        # TODO: Put group in error state if delete fails
        d.addErrback(log.err, 'Could not delete server in error', server_id=server_id)
        deferreds.append(d) # TODO: schedule to execute state transition after some time

    return defer.gatherResults(deferreds, consumeErrors=True)


def check_times(log, state):
    """
    Check the time since servers has been building and deleting. If they take too long,
    delete them
    """
    deferreds = []
    for server_id, info in state.pending.items():
        if datetime.utcnow() - info['created_at'] > timedelta(hours=1):
            log.err('server building for too long', server_id=server_id)
            d = supervisor.delete_server(server_id)
            d.addCallback(lambda _, server_id: state.remove_pending(server_id), server_id)
            deferreds.append(d)
    for server_id, info in state.deleting.items():
        if datetime.utcnow() - info['delete_at'] > timedelta(hours=1):
            log.err('server deleting for too long', server_id=server_id)
            d = supervisor.delete_server(server_id)
            d.addCallback(lambda _, server_id: state.remove_deleting(server_id), server_id)
            deferreds.append(d)
    # TODO: If any of the delete call fails, put the group in error state
    return defer.gatherResults(deferreds, consumeErrors=True)


#------------- State transition events---------------

def group_event(group, event):
    # call any of below server change events
    # and execute state transition
    return execute_group_transition(group, state)

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
    if instance_id in state.active:
        state.remove_active(instance_id)
    elif instance_id in state.pending:
        state.remove_pending(instance_id)
    elif instance_id in state.error:
        state.remove_error(instance_id)
    elif instance_id in state.deleting:
        state.remove_deleting(instance_id)
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
    else:
        # Untracked server was building.
        log.msg('Untracked server finished building', server_id=instance_id)
    return state


def server_error(group, state, instance_id):
    """
    Called when `instance_id` server went to error state
    """
    if instance_id in state.active:
        state.remove_active(instance_id)
        state.add_error(instance_id)
    elif instance_id in state.pending:
        state.remove_pending(instance_id)
        state.add_error(instance_id)
    else:
        # ERROR: unknown server got deleted
        pass
    return state


def check_state_after(group, instance_id, server_state, timeout):
    """
    Check that state of given server `instance_id` is `server_state` after timeout
    """
    pass


def remove_scheduled_check(group, instance_id):
    """
    Remove scheduled state check for `instance_id`
    """
    pass


