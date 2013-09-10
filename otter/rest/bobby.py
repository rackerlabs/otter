"""
Temporary place for bobby globals
"""

_bobby = None


def get_bobby():
    """
    :return: The bobby instance or None
    """
    return _bobby


def set_bobby(bobby):
    """
    Sets the Bobby used in coordination.

    :param bobby: the Bobby instance used in MaaS coordination
    """
    global _bobby
    _bobby = bobby
