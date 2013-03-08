"""
The Otter Supervisor marhsals an arbitrary number of workers to
execute a launch config and bring up a server, reporting back
to the controller when the task completes

"""

from otter.util.hashkey import generate_job_id


def execute_one_config(log, transaction_id, group_uuid, launch_config):
    """
    Executes a single launch config.
    Returns a job id as soon as the job is accepted.
    job eventually calls complete_pending_job on the controller
    """
    id = generate_job_id(group_uuid)
    # Add job blob
    # Fire off job working process
    # eventually calls complete_pending_job()
    return id
