from otter.models import interface
from sqlalchemy import Column, ForeignKey, MetaData, Table
from sqlalchemy.types import Enum, Integer, String
from sqlalchemy.schema import CreateTable
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from uuid import uuid4
from zope.interface import implementer


def _with_transaction(f):
    @inlineCallbacks
    def decorated(self, *args, **kwargs):
        conn = yield self.engine.connect()
        txn = yield conn.begin()

        try:
            result = yield f(self, conn, *args, **kwargs)
        except:
            txn.rollback()
            raise
        else:
            txn.commit()
            returnValue(result)

    return decorated


@implementer(interface.IScalingGroup)
class SQLScalingGroup(object):
    """
    A scaling group backed by a SQL store.
    """
    def __init__(self, engine, tenant_id, uuid):
        self.engine = engine
        self.tenant_id = tenant_id
        self.uuid = uuid

    @_with_transaction
    def create_policies(self, conn, policy_cfgs):
        """
        Create some policies.
        """
        ds = [_create_policy(conn, cfg) for cfg in policy_cfgs]
        d = gatherResults(ds)

        @d.addCallback
        def created_policies(policy_ids):
            return [dict(id=policy_id, **policy_cfg)
                    for policy_id, policy_cfg in zip(policy_ids, policy_cfgs)]

        return d


@implementer(interface.IScalingGroupCollection)
class SQLScalingGroupCollection(object):
    """
    A collection of scaling groups backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine

    @_with_transaction
    def create_scaling_group(self, conn, log, tenant_id, config, launch,
                             policies=None):
        """
        Creates a scaling group backed by a SQL store.
        """
        group_id = bytes(uuid4())

        d = conn.execute(scaling_groups.insert()
                         .values(id=group_id,
                                 tenant_id=tenant_id,
                                 name=config["name"]))

        @d.addCallback
        def build_response(result):
            return {
                "id": group_id,
                "state": interface.GroupState(tenant_id=tenant_id,
                                              group_id=group_id,
                                              group_name=config["name"],
                                              active={},
                                              pending={},
                                              policy_touched={},
                                              group_touched={},
                                              paused=False),
                "groupConfiguration": config,
                "launchConfiguration": launch,
                "scalingPolicies": policies if policies is not None else []
            }

        return d

    def get_scaling_group(self, log, tenant_id, scaling_group_id):
        return SQLScalingGroup(self.engine, tenant_id, scaling_group_id)

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

@implementer(interface.IScalingGroup)
class SQLScalingScheduleCollection(object):
    """
    A scaling schedule collection backed by a SQL store.
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


def _create_policy(conn, policy_cfg):
    """
    Creates a single scaling policy.

    This should only ever be called within a transaction: multiple
    insert statements may be issued.
    """
    policy_id = bytes(uuid4())

    adjustment_type = _get_adjustment_type(policy_cfg)
    adjustment_value = policy_cfg[adjustment_type]

    d = conn.execute(policies.insert()
                     .values(id=policy_id,
                             name=policy_cfg["name"],
                             adjustment_type=adjustment_type,
                             adjustment_value=adjustment_value))

    args = policy_cfg.get("args")
    if args:
        d.addCallback(lambda _result: _create_policy_args(conn, policy_id, args))

    return d.addCallback(lambda _result: policy_id)


def _create_policy_args(conn, policy_id, args):
    """
    Adds args to the policy with given policy_id.
    """
    d = conn.execute(policy_args.insert(),
                     [dict(policy_id=policy_id, key=key, value=value)
                      for key, value in args.items()])
    return d


def _get_adjustment_type(policy_cfg):
    """
    Gets the adjustment type ("change", "changePercent"...) of the
    policy configuration.
    """
    adjustment_types = ["change", "changePercent", "desiredCapacity"]
    for adjustment_type in adjustment_types:
        if adjustment_type in policy_cfg:
            return adjustment_type
    else:
        raise KeyError("No adjustment_type (one of {}) in policy config {}"
                       .format(adjustment_types, policy_cfg))


metadata = MetaData()

scaling_groups = Table("scaling_groups", metadata,
                       Column("id", String(32), primary_key=True),
                       Column("name", String()),
                       Column("tenant_id", String()),
                       Column("cooldown", Integer()),
                       Column("minEntities", Integer()),
                       Column("maxEntities", Integer()))

group_metadata = Table("group_metadata", metadata,
                       Column("group_id", ForeignKey("scaling_groups.id"),
                              primary_key=True),
                       Column("key", String(), primary_key=True),
                       Column("value", String()))

policies = Table("policies", metadata,
                 Column("id", String(32), primary_key=True),
                 Column("tenant_id", String()),
                 Column("name", String()),
                 Column("adjustment_type",
                        Enum("change", "changePercent", "desiredCapacity")),
                 Column("adjustment_value", Integer()),
                 Column("type",
                        Enum("webhook", "schedule", "cloud_monitoring")))

policy_args = Table("policy_args", metadata,
                    Column("policy_id", ForeignKey("policies.id"),
                           primary_key=True),
                    Column("key", String(), primary_key=True),
                    Column("value", String()))

webhooks = Table("webhooks", metadata,
                 Column("id", Integer(), primary_key=True),
                 Column("tenant_id", String()))

load_balancers = Table("load_balancers", metadata,
                       Column("id", Integer(), primary_key=True),
                       Column("port", Integer()))

all_tables = (scaling_groups,
              policies,
              policy_args,
              webhooks,
              load_balancers)


def create_tables(engine, tables=all_tables):
    """Creates all the given tables on the given engine.

    """
    return gatherResults(engine.execute(CreateTable(table))
                         for table in tables)
