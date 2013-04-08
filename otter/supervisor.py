"""
The Otter Supervisor marhsals an arbitrary number of workers to
execute a launch config and bring up a server, reporting back
to the controller when the task completes.
"""
from twisted.internet.defer import Deferred, succeed
from otter.util.hashkey import generate_job_id

from otter.worker import launch_server_v1


def execute_config(log, transaction_id, auth_function, scaling_group, launch_config):
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
    job_id = generate_job_id(scaling_group.uuid)
    completion_d = Deferred()

    log = log.fields(job_id=job_id,
                     worker=launch_config['type'],
                     tenant_id=scaling_group.tenant_id)

    assert launch_config['type'] == 'launch_server'

    log.fields(tenant_id=scaling_group.tenant_id).info("Authenticating for tenant")

    d = auth_function(scaling_group.tenant_id)

    def launch_server((auth_token, service_catalog)):
        log.info("Executing launch config.")
        return launch_server_v1.launch_server(
            'ORD',  # TODO: Get the region probably from the config or something.
            scaling_group,
            service_catalog,
            auth_token,
            launch_config['args'])

    d.addCallback(launch_server)

    def complete_job_id(result):
        log.info("Done executing launch config.")
        # XXX: Meaningful return value?

    d.addCallback(complete_job_id)
    d.addCallbacks(completion_d.callback,
                   completion_d.errback)

    return succeed((job_id, completion_d, {}))
