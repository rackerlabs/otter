"""
Contains code to handle state transitions of the group. Will launch/delete server
and update group state to store those transitions
"""

from twisted.internet import defer

from otter.supervisor import get_supervisor


def execute_group_transition(log, group, current):
    """
    Compare the current state w.r.t what is desired and execute actions that need
    to be performed to come to desired state
    :return: deferred that fires with updated state after all actions are taken
    """
    # TODO: Decide on handling errors from executing nova calls.
    def handle_delete_errors(failures):
        """
        Decide how to handle errors occurred from calling dependent services like
        nova/loadbalancer
        """
        # For example, If API-ratelimited, then pause the group till time expires
        # Return success if you want to scale
        pass

    def handle_scale_errors(failures):
        """
        Decide how to handle errors occurring while trying to scale up/down. It could
        be same as `handle_delete_errors` above
        """
        pass

    supervisor = get_supervisor()

    # try deleting servers in error state, building for too long or deleting for too long
    dl1 = delete_unwanted_servers(log, supervisor, group, current)

    # add/remove to load balancers
    dl2 = update_load_balancers(log, supervisor, group, current)

    d = DeferredList(dl1 + dl2, consumeErrors=True).addCallback(handle_service_errors)

    def scale(_):
        current_total = len(current.active) + len(current.pending)
        if current_total == current.desired:
            return None
        elif current_total < current.desired:
            return execute_scale_up(log, supervisor, group,
                                    current, current.desired - current_total)
        else:
            return execute_scale_down(log, supervisor, group,
                                      current, current_total - current.desired)

    return d.addCallback(scale).addCallback(handle_scale_errors).addCallback(lambda _: current)


def update_load_balancers(log, supervisor, group, state):

    deferreds = []

    def remove_server(_, server_id):
        if server_id in state.deleted:
            state.remove_deleted(server_id)
        elif server_id in state.error:
            del state.error[server_id]['lb_info']
        elif server_id in state.deleting:
            del state.deleting[server_id]['lb_info']


    # TODO: Deleted servers are required only if active servers transition to 'deleted' state
    # before going to 'deleting' state. If we can guarantee that 'active' always transition to
    # 'deleting' then 'deleted' is not required
    # Remove servers from load balancers that are no longer active
    for server_id, info in itertools.chain(
        state.error.items(), state.deleting.items(), state.deleted.items()):
        if info and info.get('lb_info'):
            d = supervisor.remove_from_load_balancers(log, group, server_id, info['lb_info'])
            d.addCallback(remove_server, server_id)
            deferreds.append(d)

    # Add active servers to load balancers that are not already there
    for server_id, info in state.active.items():
        if not (info and info.get('lb_info')):
            d = supervisor.add_to_load_balancers(log, group, server_id)
            d.addCallback(lambda lb_info, server_id: state.add_lb_info(server_id, lb_info))
            deferreds.append(d)

    return deferreds


def execute_scale_up(log, supervisor, group, state, delta):
    d = group.view_launch_config()

    def launch_servers(launch_config):
        deferreds = [
            supervisor.launch_server(log, group, launch_config)
                .addCallback(lambda s: state.add_pending(s['id'], s))
            for _i in range(delta)
        ]
        return DeferredList(deferreds, consumeErrors=True)

    return d.addCallback(launch_servers)


def execute_scale_down(log, supervisor, group, state, delta):

    def server_deleted(_, server_id):
        state.remove_active(server_id)
        state.add_deleting(server_id)

    active_delete_num = delta - len(state.pending)
    if active_delete_num > 0:
        sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
        servers_to_delete = sorted_servers[:delta]
            d = [supervisor.delete_server(log, group, server['id'], server['lb_info'])
                    .addCallback(server_deleted, server['id'])
                 for server in servers_to_delete]
        return DeferredList(deferreds, consumeErrors=True)
    else:
        # Cannot delete pending servers now.
        return defer.succeed(None)


def delete_unwanted_servers(log, supervisor, group, state):
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
        if datetime.utcnow() - from_timestamp(info['created']) > timedelta(hours=1):
            log.msg('server building for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, info['lb_info'])
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(remove_pending, server_id)
            deferreds.append(d)
    for server_id in state.deleting:
        if datetime.utcnow() - from_timestamp(info['deleted']) > timedelta(hours=1):
            log.msg('server deleting for too long', server_id=server_id)
            d = supervisor.delete_server(log, group, server_id, None)
            d.addErrback(ignore_request_api_error, 404, log, 'Server already deleted',
                         server_id=server_id)
            d.addCallback(lambda _, server_id: state.remove_deleting(server_id), server_id)
            deferreds.append(d)

    #return defer.DeferredList(deferreds, consumeErrors=True)
    return deferreds
    #return d.addCallback(collect_errors)


#------------- State transition events---------------

def group_event(group, event):
    # call any of below server change events
    state = server_transition[event.type](log.bind(server_id=server_id), state, event.server_id))
    # and execute state transition
    return state and execute_group_transition(log, group, state) or defer.succeed(None)


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
    elif server_id in state.deleted:
        info = state.remove_deleted(server_id)
    else:
        raise ValueError('Unknown server_id')
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


def server_error(group, state, server_id):
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


