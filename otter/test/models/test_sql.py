from otter.models import interface, sql
from twisted.trial.unittest import SynchronousTestCase
from zope.interface.verify import verifyObject


class SQLScalingGroupTests(SynchronousTestCase):
    def test_interface(self):
        """
        The SQL scaling group implementation implements the
        :class:`interface.IScalingGroup` interface.
        """
        group = sql.SQLScalingGroup()
        verifyObject(interface.IScalingGroup, group)


class SQLScalingScheduleCollectionTests(SynchronousTestCase):
    def test_interface(self):
        """
        The SQL scaling schedule collection implementation implements the
        :class:`interface.IScalingScheduleCollection` interface.
        """
        sched_coll = sql.SQLScalingScheduleCollection()
        verifyObject(interface.IScalingScheduleCollection, sched_coll)


class SQLScalingGroupCollectionTests(SynchronousTestCase):
    def test_interface(self):
        """
        The SQL scaling group collection implementation implements the
        :class:`interface.IScalingGroupCollection` interface.
        """
        group = sql.SQLScalingGroupCollection()
        verifyObject(interface.IScalingGroupCollection, group)
