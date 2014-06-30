from otter.models import interface
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.schema import CreateTable
from twisted.internet.defer import gatherResults, maybeDeferred
from zope.interface import implementer


@implementer(interface.IScalingGroup)
class SQLScalingGroup(object):
    """
    A scaling group backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


@implementer(interface.IScalingGroup)
class SQLScalingScheduleCollection(object):
    """
    A scaling schedule collection backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


@implementer(interface.IScalingGroupCollection)
class SQLScalingGroupCollection(object):
    """
    A collection of scaling groups backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


@implementer(interface.IAdmin)
class SQLAdmin(object):
    """
    An admin interface backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


metadata = MetaData()

scaling_groups = Table("scaling_groups", metadata,
                       Column("id", Integer(), primary_key=True))

policies = Table("policies", metadata,
                 Column("id", Integer(), primary_key=True))

load_balancers = Table("load_balancers", metadata,
                       Column("id", Integer(), primary_key=True),
                       Column("port", Integer()))

all_tables = (scaling_groups, policies, load_balancers)


def create_tables(engine, tables=all_tables):
    """Creates all the given tables on the given engine.

    This returns a :class:`Deferred<twisted.internet.defer.Deferred>`
    that will fire when all the tables have been created. This is only
    actually asynchronous if the provided engine is asynchronous. If
    you're using a regular SQLAlchemy engine, this will still block,
    despite returning a Deferred!

    """
    return gatherResults(maybeDeferred(CreateTable, t) for t in tables)
