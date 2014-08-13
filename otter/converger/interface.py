"""
Interfaces for convergence.
"""
from zope.interface import Interface

class IConverger(Interface):
    """
    A converger is a continuous process that, over time, causes the
    number of machines attached to a load balancer to converge to a
    fixed value.
    """
    def schedule_convergence(load_balancer_id):
        """
        Schedules convergence for the machiens attached to the load
        balancer with the given identifier.

        :param bytes load_balancer_id: The CLB's unique identifier.
        :return: :data:`None`
        """

    def set_desired_capacity(load_balancer_id, desired_capacity):
        """Sets the desired number of machines attached to the load balancer
        with given identifier.

        :param bytes load_balancer_id: The CLB's unique identifier.
        :param int desired_capacity: The desired number of machines for the
            load balancer.
        :raises ValueError: (synchronously) If the given desired
            capacity is impossible, e.g. negative or larger than some
            system-wide limit.
        :return: :data:`None`
        """
