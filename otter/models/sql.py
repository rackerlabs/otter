from otter.models import interface
from sqlalchemy import Column, Enum, Integer, MetaData, String, Table
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


    def create_scaling_group(self, log, tenant_id, group_cfg, launch_cfg,
                             policies=None):
        """
        Creates a scaling group backed by a SQL store.
        """

    def get_counts(self, log, tenant_id):
        statements = [t.select().where(t.c.tenant_id == tenant_id).count()
                      for t in [scaling_groups, policies, webhooks]]

        d = gatherResults(map(self.engine.execute, statements))

        @d.addCallback
        def query_executed(results):
            return gatherResults([r.fetchone() for r in results])

        @d.addCallback
        def query_executed(results):
            (groups,), (policies,), (webhooks,) = results
            return dict(groups=groups, policies=policies, webhooks=webhooks)

        return d


def _create_policy(conn, policy_cfg):
    """
    Creates a single scaling policy.

    This should only ever be called within a transaction: multiple
    insert statements may be issued.
    """
    effect_names = ["change", "changePercent", "desiredCapacity"]
    for effect_namein effect_names:
        if effect_namein policy_cfg:
            break
    else:
        raise KeyError("No effect (one of {}) in policy config {}"
                       .format(effect_names, policy_cfg))

    d = conn.execute(policies.insert()
                     .values(effect=effect,
                             value=policy_cfg["value"]))

    if "args" not in policy_cfg:
        return d

    # How do I know what the primary key is going to be here? Nested
    # txns? UUIDs?
    pkey = None

    ds = [d]
    for key, value in policy_cfg["args"].items():
        ds.append(conn.execute(policy_args))

    return gatherResults(ds)


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
                 Column("name", String()),
                 Column("tenant_id", String()),
                 Column("effect", Enum("change", "changePercent", "desiredCapacity")),
                 Column("value", Integer()),
                 Column("type", Enum("webhook", "schedule", "cloud_monitoring")))

policy_args = Table("policy_args", metadata,
                    Column("id", Integer(), primary_key=True),
                    Column("policy_id", ForeignKey("policies.id")),
                    Column("key", String()),
                    Column("value", String()))

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
