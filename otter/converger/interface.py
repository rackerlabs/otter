"""
Interfaces for convergence.
"""
from zope.interface import Interface


class IConverger(Interface):
    """
    A converger is a continuous process that, over time, causes the
    number of machines in a scaling group to converge to a fixed
    value.
    """
    def schedule_convergence(group_id):
        """Schedules convergence for the machines in a scaling group.

        :param bytes group_id: The group's unique identifier.
        :return: :data:`None`
        """

    def set_desired_capacity(group_id, desired_capacity):
        """Sets the desired number of machines in a scaling group.

        :param bytes group_id: The group's unique identifier.
        :param int desired_capacity: The desired number of machines for the
            load balancer.
        :raises ValueError: (synchronously) If the given desired
            capacity is impossible, e.g. negative or larger than some
            system-wide limit.
        :return: :data:`None`
        """
