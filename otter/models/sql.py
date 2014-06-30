from otter.models import interface
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql import func, select
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


    def get_counts(self, log, tenant_id):
        # FIXME: do something with log

        import pudb; pudb.set_trace()

        statements = [t.select().where(t.c.tenant_id == tenant_id).count()
                      for t in [scaling_groups, policies, webhooks]]

        d = gatherResults(map(self.engine.execute, statements))

        @d.addCallback
        def query_executed(result):
            return {"groups": result[0],
                    "policies": result[1],
                    "webhooks": result[2]}

        return d


@implementer(interface.IAdmin)
class SQLAdmin(object):
    """
    An admin interface backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


metadata = MetaData()

scaling_groups = Table("scaling_groups", metadata,
                       Column("id", Integer(), primary_key=True),
                       Column("tenant_id", String()))

policies = Table("policies", metadata,
                 Column("id", Integer(), primary_key=True),
                 Column("tenant_id", String()))

webhooks = Table("webhooks", metadata,
                 Column("id", Integer(), primary_key=True),
                 Column("tenant_id", String()))

load_balancers = Table("load_balancers", metadata,
                       Column("id", Integer(), primary_key=True),
                       Column("port", Integer()))

all_tables = (scaling_groups, policies, webhooks, load_balancers)


def create_tables(engine, tables=all_tables):
    """Creates all the given tables on the given engine.

    """
    return gatherResults(engine.execute(CreateTable(table))
                         for table in tables)
