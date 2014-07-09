from collections import defaultdict
from operator import methodcaller
from otter.models import interface
from sqlalchemy import Column, ForeignKey, MetaData, Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import Enum, Integer, String
from sqlalchemy.schema import CreateTable
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.internet.defer import FirstError
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
        ds = [_create_policy(conn, self.tenant_id, self.uuid, cfg)
              for cfg in policy_cfgs]
        d = gatherResults(ds, consumeErrors=True)

        @d.addCallback
        def created_policies(policy_ids):
            return [dict(id=policy_id, **policy_cfg)
                    for policy_id, policy_cfg in zip(policy_ids, policy_cfgs)]

        @d.addErrback
        def check_if_group_exists(f):
            f.trap(FirstError)

            subFailure = f.value.subFailure
            subFailure.trap(IntegrityError)

            raise interface.NoSuchScalingGroupError(self.tenant_id, self.uuid)

        return d

    @_with_transaction
    def list_policies(self, conn, limit=100, marker=None):
        """
        List up to *limit* policies, starting with id *marker*.
        """
        # TODO: only for this tenant & group!
        c = policies.c
        query = policies.select().order_by(c.id).limit(limit)
        if marker is not None:
            query = query.where(c.id > marker)

        d = conn.execute(query).addCallback(_fetchall)

        @d.addCallback
        def get_policy_args(policy_rows):
            policy_ids = [r[c.id] for r in policy_rows]
            d = _get_policy_args(conn, policy_ids)
            d.addCallback(lambda args_by_policy: (policy_rows, args_by_policy))
            return d

        @d.addCallback
        def format_result(result):
            policy_rows, args_by_policy = result

            policies = []
            for r in policy_rows:
                policy = {"id": r[c.id],
                          "name": r[c.name],
                          "type": r[c.type],
                          r[c.adjustment_type]: r[c.adjustment_value],
                          "cooldown": r[c.cooldown]}

                args = args_by_policy.get(policy["id"])
                if args is not None:
                    policy["args"] = args

                policies.append(policy)

            return policies

        return d


def _get_policy_args(conn, policy_ids):
    """
    Gets the policy args for the given policies.

    :return: A dictionary of all the policy args for the given policies.
    :rtype: mapping ``{policy_id: {key: value}}``
    """
    q = policy_args.select(policy_args.c.policy_id.in_(policy_ids))
    d = conn.execute(q).addCallback(_fetchall)

    @d.addCallback
    def format_args(rows):
        args_by_policy = defaultdict(dict)
        for row in rows:
            c = policy_args.c
            policy_id, key, value = row[c.policy_id], row[c.key], row[c.value]
            args_by_policy[policy_id][key] = value

        return args_by_policy

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


def _create_policy(conn, tenant_id, group_id, policy_cfg):
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
                             tenant_id=tenant_id,
                             group_id=group_id,
                             name=policy_cfg["name"],
                             adjustment_type=adjustment_type,
                             adjustment_value=adjustment_value,
                             type=policy_cfg["type"],
                             cooldown=policy_cfg["cooldown"]))

    args = policy_cfg.get("args")
    if args:
        d.addCallback(lambda _result: _create_policy_args(conn, policy_id, args))

    return d.addCallback(lambda _result: policy_id)


def _create_policy_args(conn, policy_id, args):
    """
    Adds args to the policy with given policy_id.
    """
    row_data = [dict(policy_id=policy_id, key=key, value=value)
                for key, value in args.items()]
    return conn.execute(policy_args.insert(), row_data)


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
                 Column("tenant_id", String(), nullable=False),
                 Column("group_id", ForeignKey("scaling_groups.id"),
                        nullable=False),
                 Column("name", String(), nullable=False),
                 Column("adjustment_type",
                        Enum("change", "changePercent", "desiredCapacity"),
                        nullable=False),
                 Column("adjustment_value", Integer(),
                        nullable=False),
                 Column("type",
                        Enum("webhook", "schedule", "cloud_monitoring"),
                        nullable=False),
                 Column("cooldown", Integer(), nullable=False))

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

_fetchall = methodcaller("fetchall")
