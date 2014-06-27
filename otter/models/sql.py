from otter.models.interface import IScalingGroup
from zope.interface import implementer


@implementer(IScalingGroup)
class SQLScalingGroup(object):
    pass
