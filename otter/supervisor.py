"""
The Otter Supervisor manages a number of workers to execute a launch config.
"""

from twisted.internet.defer import Deferred, succeed
from otter.util.hashkey import generate_job_id

from otter.util.config import config_value
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

    log = log.bind(job_id=job_id,
                   worker=launch_config['type'],
                   tenant_id=scaling_group.tenant_id)

    assert launch_config['type'] == 'launch_server'

    log.msg("Authenticating for tenant")

    d = auth_function(scaling_group.tenant_id)

    def when_authenticated((auth_token, service_catalog)):
        log.msg("Executing launch config.")
        return launch_server_v1.launch_server(
            log,
            config_value('region'),
            scaling_group,
            service_catalog,
            auth_token,
            launch_config['args'])

    d.addCallback(when_authenticated)

    def when_launch_server_completed(result):
        # XXX: Something should be done with this data. Currently only enough
        # to pass to the controller to store in the active state is returned
        server_details, lb_info = result
        log.msg("Done executing launch config.",
                instance_id=server_details['server']['id'])
        return {
            'id': server_details['server']['id'],
            'links': server_details['server']['links'],
            'name': server_details['server']['name']
        }

    d.addCallback(when_launch_server_completed)
    d.chainDeferred(completion_d)

    return succeed((job_id, completion_d))
