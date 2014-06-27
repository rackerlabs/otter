from otter.models import sql
from otter.models.interface import IScalingGroup
from twisted.trial.unittest import SynchronousTestCase
from zope.interface.verify import verifyObject


class SQLScalingGroupTests(SynchronousTestCase):
    def test_interface(self):
        """
        The SQL scaling group implementation implements :class:`IScalingGroup`.
        """
        group = sql.SQLScalingGroup()
        verifyObject(IScalingGroup, group)
