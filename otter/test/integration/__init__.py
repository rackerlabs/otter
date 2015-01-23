"""
Black-box integration testing of convergence.
"""


def measure_progress(previous_state, current_state, desired_state):
    """
    How many steps have been made towards the desired state between
    the previous and current states?

    :param previous_state: The previous state of a scaling group.
    :param current_state: The current state of a scaling group.
    :param desired_state: The desired state of a scaling group.
    :return: The number of steps made towards the desired.
    :rtype: int
    """
