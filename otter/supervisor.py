"""
The Otter Supervisor manages a number of workers to execute a launch config.

This code is specific to the launch_server_v1 worker.
"""

from twisted.application.service import Service
from twisted.internet.defer import succeed

from zope.interface import Interface, implementer

from otter.models.interface import NoSuchScalingGroupError
from otter.log import audit
from otter.util.deferredutils import DeferredPool
from otter.util.hashkey import generate_job_id
from otter.util.timestamp import from_timestamp
from otter.worker import launch_server_v1, validate_config
from otter.undo import InMemoryUndoStack


class ISupervisor(Interface):
    """
    Supervisor that manages launch configuration execution jobs and server
    deletion jobs.
    """

    def execute_config(log, transaction_id, scaling_group, launch_config):
        """
        Executes a single launch config.

        :param log: Bound logger.
        :param str transaction_id: Transaction ID.
        :param callable auth_function: A 1-argument callable that takes a tenant_id,
            and returns a Deferred that fires with a 2-tuple of auth_token and
            service_catalog.
        :param IScalingGroup scaling_group: Scaling Group.
        :param dict launch_config: The launch config for the scaling group.

        :returns: A deferred that fires with a 3-tuple of job_id, completion deferred,
            and job_info (a dict)
        :rtype: ``Deferred``
        """

    def execute_delete_server(log, transaction_id, scaling_group, server):
        """
        Executes a single delete server

        :param log: Bound logger.
        :param str transaction_id: Transaction ID.
        :param IScalingGroup scaling_group: Scaling Group.
        :param dict server: The server details (containing the ID, and what
            load balancers it has been added to) so that it can be deleted

        :returns: ``Deferred`` that callbacks with None after the server
            has been deleted successfully.  None is also callback(ed) when
            server deletion fails in which case the error is logged
            before callback(ing).
        """


@implementer(ISupervisor)
class SupervisorService(object, Service):
    """
    A service which manages execution of launch configurations.

    :ivar callable auth_function: authentication function to use to obtain an
        auth token and service catalog.  Should accept a tenant ID.

    :ivar callable coiterate: coiterate function that will be passed to
        InMemoryUndoStack.

    :ivar DeferredPool deferred_pool: a pool in which to store deferreds that
        should be waited on
    """
    name = "supervisor"

    def __init__(self, auth_function, region, coiterate):
        self.auth_function = auth_function
        self.region = region
        self.coiterate = coiterate
        self.deferred_pool = DeferredPool()

    def execute_config(self, log, transaction_id, scaling_group, launch_config):
        """
        see :meth:`ISupervisor.execute_config`
        """
        log = log.bind(worker=launch_config['type'],
                       tenant_id=scaling_group.tenant_id)

        assert launch_config['type'] == 'launch_server'

        undo = InMemoryUndoStack(self.coiterate)

        log.msg("Authenticating for tenant")

        d = self.auth_function(scaling_group.tenant_id, log=log)

        def when_authenticated((auth_token, service_catalog)):
            log.msg("Executing launch config.")
            return launch_server_v1.launch_server(
                log,
                self.region,
                scaling_group,
                service_catalog,
                auth_token,
                launch_config['args'], undo)

        d.addCallback(when_authenticated)

        def when_launch_server_completed(result):
            # XXX: Something should be done with this data. Currently only enough
            # to pass to the controller to store in the active state is returned
            server_details, lb_info = result
            log.msg("Done executing launch config.",
                    server_id=server_details['server']['id'])
            return {
                'id': server_details['server']['id'],
                'links': server_details['server']['links'],
                'name': server_details['server']['name'],
                'lb_info': lb_info
            }

        d.addCallback(when_launch_server_completed)

        def when_fails(result):
            log.msg("Encountered an error, rewinding {worker!r} job undo stack.",
                    exc=result.value)
            ud = undo.rewind()
            ud.addCallback(lambda _: result)
            return ud

        d.addErrback(when_fails)
        return d

    def execute_delete_server(self, log, transaction_id, scaling_group, server):
        """
        see :meth:`ISupervisor.execute_delete_server`
        """
        log = log.bind(server_id=server['id'], tenant_id=scaling_group.tenant_id)

        # authenticate for tenant
        def when_authenticated((auth_token, service_catalog)):
            return launch_server_v1.delete_server(
                log,
                self.region,
                service_catalog,
                auth_token,
                (server['id'], server['lb_info']))

        d = self.auth_function(scaling_group.tenant_id, log=log)
        log.msg("Authenticating for tenant")
        d.addCallback(when_authenticated)

        return d

    def validate_launch_config(self, log, tenant_id, launch_config):
        """
        Validate launch config for a tenant
        """
        def when_authenticated((auth_token, service_catalog)):
            log.msg('Validating launch server config')
            return validate_config.validate_launch_server_config(
                log,
                self.region,
                service_catalog,
                auth_token,
                launch_config['args'])

        if launch_config['type'] != 'launch_server':
            raise NotImplementedError('Validating launch config for launch_server only')

        log = log.bind(system='otter.supervisor.validate_launch_config',
                       tenant_id=tenant_id)
        d = self.auth_function(tenant_id, log=log)
        log.msg('Authenticating for tenant')
        return d.addCallback(when_authenticated)

    def stopService(self):
        """
        Returns a deferred that succeeds when the :class:`DeferredPool` is
        empty
        """
        super(SupervisorService, self).stopService()
        return self.deferred_pool.notify_when_empty()

    def health_check(self):
        """
        Check if supervisor is healthy. In this case, just return number of jobs
        currently running.
        """
        return True, {'jobs': len(self.deferred_pool)}


_supervisor = None


def get_supervisor():
    """
    Get the current supervisor.
    """
    return _supervisor


def set_supervisor(supervisor):
    """
    Set the current supervisor.
    """
    global _supervisor
    _supervisor = supervisor


def find_pending_jobs_to_cancel(log, state, delta):
    """
    Identify some pending jobs to cancel (usually for a scale down event)
    """
    if delta >= len(state.pending):  # don't bother sorting - return everything
        return state.pending.keys()

    sorted_jobs = sorted(state.pending.items(), key=lambda (_id, s): from_timestamp(s['created']),
                         reverse=True)
    return [job_id for job_id, _job_info in sorted_jobs[:delta]]


def find_servers_to_evict(log, state, delta):
    """
    Find the servers most appropriate to evict from the scaling group

    Returns list of server ``dict``
    """
    if delta >= len(state.active):  # don't bother sorting - return everything
        return state.active.values()

    # return delta number of oldest server
    sorted_servers = sorted(state.active.values(), key=lambda s: from_timestamp(s['created']))
    return sorted_servers[:delta]


def delete_active_servers(log, transaction_id, scaling_group,
                          delta, state):
    """
    Start deleting active servers jobs
    """

    # find servers to evict
    servers_to_evict = find_servers_to_evict(log, state, delta)

    # remove all the active servers to be deleted
    for server in servers_to_evict:
        state.remove_active(server['id'])

    # then start deleting those servers
    supervisor = get_supervisor()
    for i, server_info in enumerate(servers_to_evict):
        job = _DeleteJob(log, transaction_id, scaling_group, server_info, supervisor)
        supervisor.deferred_pool.add(job.start())


def exec_scale_down(log, transaction_id, state, scaling_group, delta):
    """
    Execute a scale down policy
    """

    # cancel pending jobs by removing them from the state. The servers will get
    # deleted when they are finished building and their id is not found in pending
    jobs_to_cancel = find_pending_jobs_to_cancel(log, state, delta)
    for job_id in jobs_to_cancel:
        state.remove_job(job_id)

    # delete active servers if pending jobs are not enough
    remaining_to_delete = delta - len(jobs_to_cancel)
    if remaining_to_delete > 0:
        delete_active_servers(log, transaction_id,
                              scaling_group, remaining_to_delete, state)

    log.msg("Deleting {delta} servers.", delta=delta, **_log_capacity(state))

    return succeed(None)


def _log_capacity(state):
    """
    Produces a dictionary containing the active capacity, pending capacity, and
    desired capacity (which is what the user requested, not active + pending),
    to be used for logging.

    This exists because the current_desired presented to users is active +
    pending, and we want these keywords to be filtered out of the audit logs
    for now until desired capacity is consistent between the state API
    response and the audit log/this.
    """
    return {
        'current_active': len(state.active),
        'current_pending': len(state.pending),
        'current_desired': state.desired
    }


class _DeleteJob(object):
    """
    Server deletion job
    """

    def __init__(self, log, transaction_id, scaling_group, server_info, supervisor):
        """
        :param log: a bound logger instance that can be used for logging
        :param str transaction_id: a transaction id
        :param IScalingGroup scaling_group: the scaling group from where the server
                    is deleted
        :param dict server_info: a `dict` of server info
        """
        self.log = log.bind(system='otter.job.delete', server_id=server_info['id'])
        self.trans_id = transaction_id
        self.scaling_group = scaling_group
        self.server_info = server_info
        self.supervisor = supervisor

    def start(self):
        """
        Start the job
        """
        d = self.supervisor.execute_delete_server(
            self.log, self.trans_id, self.scaling_group, self.server_info)
        d.addCallback(self._job_completed)
        d.addErrback(self._job_failed)
        self.log.msg('Started server deletion job')
        return d

    def _job_completed(self, _):
        audit(self.log).msg('Server deleted.', event_type="server.delete")

    def _job_failed(self, failure):
        # REVIEW: Logging this as err since failing to delete a server will cost
        # money to customers and affect us. We should know and try to delete it manually asap
        self.log.err(failure, 'Server deletion job failed')


class _Job(object):
    """
    Private class representing a server creation job.  This calls the supervisor
    to create one server, and also handles job completion.
    """
    def __init__(self, log, transaction_id, scaling_group, supervisor):
        """
        :param log: a bound logger instance that can be used for logging
        :param str transaction_id: a transaction id
        :param IScalingGroup scaling_group: the scaling group for which a job
            should be created
        :param dict launch_config: the launch config to scale up a server
        """
        self.log = log.bind(system='otter.job.launch')
        self.transaction_id = transaction_id
        self.scaling_group = scaling_group
        self.supervisor = supervisor
        self.job_id = None

    def start(self, launch_config):
        """
        Kick off a job by calling the supervisor with a launch config.
        """
        try:
            image = launch_config['args']['server']['imageRef']
        except:
            image = 'Unable to pull image ref.'

        try:
            flavor = launch_config['args']['server']['flavorRef']
        except:
            flavor = 'Unable to pull flavor ref.'

        self.job_id = generate_job_id(self.scaling_group.uuid)
        self.log = self.log.bind(image_ref=image, flavor_ref=flavor, job_id=self.job_id)

        d = self.supervisor.execute_config(
            self.log, self.transaction_id, self.scaling_group, launch_config)
        d.addCallbacks(self._job_succeeded, self._job_failed)
        d.addErrback(self.log.err)

        return d

    def _job_failed(self, f):
        """
        Job has failed. Remove the job, if it exists, and log the error.
        """
        def handle_failure(group, state):
            # if it is not in pending, then the job was probably deleted before
            # it got a chance to fail.
            if self.job_id in state.pending:
                state.remove_job(self.job_id)
            self.log.err(f, 'Launching server failed', **_log_capacity(state))
            return state

        d = self.scaling_group.modify_state(handle_failure)

        def ignore_error_if_group_deleted(f):
            f.trap(NoSuchScalingGroupError)
            self.log.msg("Relevant scaling group has already been deleted. "
                         "Job failure logged and ignored.")

        d.addErrback(ignore_error_if_group_deleted)
        return d

    def _job_succeeded(self, result):
        """
        Job succeeded. If the job exists, move the server from pending to active
        and log.  If not, then the job has been canceled, so delete the server.
        """
        server_id = result['id']
        log = self.log.bind(server_id=server_id)

        def handle_success(group, state):
            if self.job_id not in state.pending:
                # server was slated to be deleted when it completed building.
                # So, deleting it now
                audit(log).msg(
                    "A pending server that is no longer needed is now active, "
                    "and hence deletable.  Deleting said server.",
                    event_type="server.deletable", **_log_capacity(state))

                job = _DeleteJob(self.log, self.transaction_id,
                                 self.scaling_group, result, self.supervisor)
                d = job.start()
                self.supervisor.deferred_pool.add(d)
            else:
                state.remove_job(self.job_id)
                state.add_active(result['id'], result)
                audit(log).msg("Server is active.", event_type="server.active",
                               **_log_capacity(state))
            return state

        d = self.scaling_group.modify_state(handle_success)

        def delete_if_group_deleted(f):
            f.trap(NoSuchScalingGroupError)
            audit(log).msg(
                "A pending server belonging to a deleted scaling group "
                "({scaling_group_id}) is now active, and hence deletable. "
                "Deleting said server.",
                event_type="server.deletable")

            job = _DeleteJob(self.log, self.transaction_id,
                             self.scaling_group, result, self.supervisor)
            d = job.start()
            self.supervisor.deferred_pool.add(d)

        d.addErrback(delete_if_group_deleted)
        return d


def execute_launch_config(log, transaction_id, state, launch, scaling_group, delta):
    """
    Execute a launch config some number of times.
    """
    log.msg("Launching {delta} servers.", delta=delta)
    supervisor = get_supervisor()
    for i in range(delta):
        job = _Job(log, transaction_id, scaling_group, supervisor)
        d = job.start(launch)
        state.add_job(job.job_id)
        # Add the job to the pool to ensure otter does not shut down until job is completed
        supervisor.deferred_pool.add(d)

    #TODO: Doing this to not cause change in controller but would be nice to remove it
    return succeed(None)


class ServerNotFoundError(Exception):
    """
    Exception to be raised when the given server is not found
    """
    def __init__(self, tenant_id, group_id, server_id):
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.server_id = server_id
        super(ServerNotFoundError, self).__init__(
            "Active server {} not found in tenant {}'s group {}".format(
                server_id, tenant_id, group_id))


class CannotDeleteServerBelowMinError(Exception):
    """
    Exception to be raised when server cannot be removed from the group
    if it will be below minimum servers in the group
    """
    def __init__(self, tenant_id, group_id, server_id, min_servers):
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.server_id = server_id
        self.min_servers = min_servers
        super(CannotDeleteServerBelowMinError, self).__init__(
            ("Cannot remove server {server_id} from tenant {tenant_id}'s group {group_id}. "
             "It will reduce number of servers below required minimum {min_servers}.").format(
                 server_id=server_id, min_servers=min_servers,
                 tenant_id=tenant_id, group_id=group_id))


def remove_server_from_group(log, trans_id, server_id, replace, group, state):
    """
    Remove specific server from the group and optionally replace it by creatig new
    server

    :param log: A bound logger
    :param trans_id: transaction id for this operation
    :param server_id: ID of server to be removed
    :param replace: Should the server be replaced?
    :param group: A :class:`otter.models.interface.IScalingGroup` implementation
    :param state: A :class:`otter.models.interface.GroupState` object

    :return: Deferred that fires with updated state object
    """

    def reduce_desired(config):
        if len(state.active) + len(state.pending) == config['minEntities']:
            raise CannotDeleteServerBelowMinError(
                group.tenant_id, group.uuid, server_id, config['minEntities'])
        else:
            state.desired -= 1

    def remove_server(_):
        server_info = state.active[server_id]
        state.remove_active(server_id)
        supervisor = get_supervisor()
        d = _DeleteJob(log, trans_id, group, server_info, supervisor).start()
        supervisor.deferred_pool.add(d)
        return state

    if server_id in state.active:
        if replace:
            d = group.view_launch_config()
            d.addCallback(lambda lc: execute_launch_config(log, trans_id, state, lc, group, 1))
        else:
            # Before reducing servers, check if it is below minimum required servers
            d = group.view_config()
            d.addCallback(reduce_desired)
        return d.addCallback(remove_server)
    else:
        raise ServerNotFoundError(group.tenant_id, group.uuid, server_id)
