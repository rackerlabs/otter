"""
Contains code to handle state transitions of the group. Will launch/delete server
and update group state to store those transitions
"""

def execute_group_transition(log, group, current):
    """
    Compare the current state w.r.t what is desired and execute actions that need
    to be performed to come to desired state
    :return: deferred that fires with updated state after all actions are started
    """
    # TODO: Consider adding to load balancer also

    # TODO: Decide on handling errors from executing nova calls.
    def handle_service_errors(failures):
        """
        Decide how to handle errors occurred from calling dependent services like
        nova/loadbalancer
        """
        # For example, If API-ratelimited, then pause the group till time expires
        # Return success if you want to scale
        pass

    # try deleting servers in error state, building for too long or deleting for too long
    d = delete_unwanted_servers(log, group, current)
    d.addCallback(handle_service_errors)

    def scale(_):
        current_total = len(current.active) + len(current.pending)
        if current_total == current.desired:
            return None
        elif current_total < current.desired:
            return execute_scale_up(log, group, current, current.desired - current_total)
        else:
            return execute_scale_down(log, group, current, current_total - current.desired)

    return d.addCallback(scale).addCallback(lambda _: current)


def execute_scale_up(log, group, state, delta):
    d = group.view_launch_config()

    def launch_servers(launch_config):
        deferreds = [
            supervisor.launch_server(log, group, launch_config)
                .addCallback(lambda s: state.add_pending(s['id'], s))
            for _i in range(delta)
        ]
        return DeferredList(deferreds, consumeErrors=True)

    return d.addCallback(launch_servers)


def execute_scale_down(state, delta):

    active_delete_num = delta - len(state.pending)
    if active_delete_num > 0:
        sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
        servers_to_delete = sorted_servers[:delta]
        deferreds =  [supervisor.delete_server(log, group, server)
                                .addCallback(partial(state.remove_active, server['id']))
                      for server in servers_to_delete]
        return DeferredList(deferreds, consumeErrors=True)
    else:
        # Cannot delete pending servers now.
        return defer.succeed(None)


def delete_unwanted_servers(log, group, state):
    """
    Delete servers building for too long, deleting for too long and servers in error state

    Return DeferredList of all the delete calls
    """

    def remove_error(_, server_id):
        state.remove_error(server_id)
        state.add_deleting(server_id)

    def remove_pending(_, server_id):
        state.remove_pending(server_id)
        state.add_deleting(server_id)

    deferreds = []
    for server_id, info in state.error.items():
        d = supervisor.delete_server(
            log, group, server_id, info.get('lb_info')).addCallback(remove_error, server_id)
        # TODO: Put group in error state if delete fails
        d.addErrback(log.err, 'Could not delete server in error', server_id=server_id)
        deferreds.append(d) # TODO: schedule to execute state transition after some time
    for server_id, info in state.pending.items():
        if datetime.utcnow() - from_timestamp(info['created_at']) > timedelta(hours=1):
            log.msg('server building for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, info['lb_info'])
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(remove_pending, server_id)
            deferreds.append(d)
    for server_id in state.deleting:
        if datetime.utcnow() - from_timestamp(info['deleted_at']) > timedelta(hours=1):
            log.msg('server deleting for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, None)
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(lambda _, server_id: state.remove_deleting(server_id), server_id)
            deferreds.append(d)

    d = defer.DeferredList(deferreds, consumeErrors=True)
    return d
    #return d.addCallback(collect_errors)


#------------- State transition events---------------

def group_event(group, event):
    # call any of below server change events
    log = log.bind(server_id=server_id)
    state = server_transition[event.type](state, event.server_id)
    # and execute state transition
    return state and execute_group_transition(group, state) or defer.succeed(None)


def remove_server(log, state, server_id):
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
    else:
        return None
    return info


def server_created(group, state, server_id):
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
    server_info = remove_server(state, server_id)
    if not server_info:
        # ERROR. A server we did not track got deleted
        log.msg('Untracked server deleted')
        return None
    return state


def server_deleting(log, group, state, server_id):
    """
    Called when a server `server_id` has started deleting
    """
    server_info = remove_server(state, server_id)
    if server_info:
        state.add_deleting(server_id, info)
        return state


def server_active(log, group, state, server_id):
    """
    Called when `server_id` server has finished building
    """
    if server_id in state.active:
        # Already active. Do nothing
        return None
    if server_id in state.pending:
        add_to_load_balancers(server_id)
        state.move_to_active(server_id)
    else:
        # Untracked server was building.
        log.msg('Untracked server finished building', server_id=server_id)
        return None
    return state


def server_error(group, state, server_id):
    """
    Called when `server_id` server went to error state
    """
    if server_id in state.active:
        state.remove_active(server_id)
        state.add_error(server_id)
    elif server_id in state.pending:
        state.remove_pending(server_id)
        state.add_error(server_id)
    elif server_id in state.deleting:
        # TODO Can this happen? A server from deleting goto error
        state.remove_deleting(server_id)
        state.add_error(server_id)
    else:
        # ERROR: unknown server got deleted
        log.msg('Untracked server errored', server_id=server_id)
        return None
    return state


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


