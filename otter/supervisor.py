"""
Spike for the scaling supervisor (that coordinates the workers)
"""

import time


def notify_group_size_change(transaction_id, scaling_group, policy_id=None):
    """
    Check steady state number, check active+pending number, either spin up
    enough servers or spin down enough servers to make the active+pending number
    equal the steady state number

    This fake code is behavings ``boot_servers`` and ``kill_servers`` is
    synchronous (so ``record_policy_completion_time`` is only called when
    they have finished executing)
    """
    magnitude = calculate_change_magnitude(scaling_group)
    if magnitude > 0:
        boot_servers(magnitude, scaling_group)
    else:
        kill_servers(magnitude)

    if magnitude != 0 and policy_id is not None:
        record_policy_completion_time(scaling_group, policy_id, time.time())


def calculate_change_magnitude(scaling_group):
    """
    :return: the difference between the steady state number and the
        (active + pending) numbers
    """
    raise NotImplementedError()


def boot_servers(number, scaling_group):
    """
    Starts ``number`` of servers using ``scaling_group``'s launch config - this
    probably starts up ``number`` of scaling workers
    """
    raise NotImplementedError()


def kill_servers(number):
    """
    Kills ``number`` number of servers
    """
    raise NotImplementedError()


def record_policy_completion_time(scaling_group, policy_id, timestamp):
    """
    Stores the time the policy was finished executing
    """
    raise NotImplementedError()
