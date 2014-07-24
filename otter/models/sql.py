"""
A data store for otter, backed by a SQL database.
"""
from collections import defaultdict
from functools import partial
from operator import methodcaller
from otter.models import interface as iface
from otter.util.config import config_value
from sqlalchemy import Column, ForeignKey, MetaData, Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import Enum, Integer, String
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql import and_, exists, select
from twisted.internet.defer import succeed
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import gatherResults, FirstError
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


@implementer(iface.IScalingGroup)
class SQLScalingGroup(object):
    """
    A scaling group backed by a SQL store.
    """
    def __init__(self, engine, tenant_id, uuid):
        self.engine = engine
        self.tenant_id = tenant_id
        self.uuid = uuid

    def _verify_group_exists(self, conn):
        d = _verify_group_exists(conn, self.tenant_id, self.uuid)
        return d

    def _verify_policy_exists(self, conn, policy_id):
        d = _verify_policy_exists(conn, self.tenant_id, self.uuid, policy_id)
        return d

    def _complain_if_missing_policy(self, result_proxy, conn, policy_id):
        """If no rows matched, the policy doesn't exist.

        That could be just because this policy doesn't exist, or because the
        group doesn't even exist. Check if the group exists, and raise
        :class:`~iface.NoSuchPolicyError` or
        :class:`~iface.NoSuchScalingGroupError` accordingly.

        """
        if result_proxy.rowcount == 0:
            d = self._verify_group_exists(conn)

            @d.addCallback
            def okay_so_the_group_exists_but_policy_doesnt(res):
                raise iface.NoSuchPolicyError(self.tenant_id, self.uuid, policy_id)

            return d

        return result_proxy

    @_with_transaction
    @inlineCallbacks
    def view_manifest(self, conn, with_webhooks=False):
        """
        See :meth:`~iface.IScalingGroup.view_manifest`.
        """
        group_configuration = yield self._get_config(conn)
        launch_configuration = yield self._get_launch_config(conn)
        scaling_policies = yield self.list_policies()

        returnValue({
            "id": self.uuid,
            "state": None,  # REVIEW: welp I can pretty much put whatever I want here right
            "groupConfiguration": group_configuration,
            "launchConfiguration": launch_configuration,
            "scalingPolicies": scaling_policies
        })

    @_with_transaction
    def view_config(self, conn):
        """
        See :meth:`~iface.IScalingGroup.view_config`.
        """
        return self._get_config(conn)

    def _get_config(self, conn):
        """
        Gets the scaling group configuration for this scaling group.

        This is separated from :meth:`view_config` so that other methods that
        already have a transaction laying around can do it within that
        transaction, using the database connection *conn*.

        :param conn: The database connection to use.
        """
        query = (scaling_groups.select()
                 .where(scaling_groups.c.id == self.uuid)
                 .limit(1))
        d = conn.execute(query).addCallback(_fetchone)

        @d.addCallback
        def format(row):
            if row is None:
                raise iface.NoSuchScalingGroupError(self.tenant_id, self.uuid)

            keys = ['cooldown', 'maxEntities', 'minEntities', 'name']
            return {key: row[key] for key in keys}

        @d.addCallback
        def add_metadata(result):
            d = _get_group_metadata(conn, self.uuid)

            def format_metadata(metadata, result):
                result["metadata"] = metadata
                return result
            d.addCallback(format_metadata, result)

            return d

        return d

    @_with_transaction
    def view_launch_config(self, conn):
        """
        See :meth:`~iface.IScalingGroup.view_launch_config`.
        """
        return self._get_launch_config(conn)

    @inlineCallbacks
    def _get_launch_config(self, conn):
        """
        Gets the launch configuration for this scaling group.

        This is separated from :meth:`view_launch_config` so that other
        methods that already have a transaction laying around can do it within
        that transaction, using the database connection *conn*.

        :param conn: The database connection to use.
        """
        def in_context(f):
            """
            Calls the function in the current context.

            Specifically, calls it with the current database connection and
            this group's UUID.
            """
            return f(conn, self.uuid)

        def get_and_maybe_add(dest, key, getter):
            result = yield in_context(getter)
            if result:
                dest[key] = result

        server = yield in_context(_get_server_payload)

        if not server:
            raise iface.NoSuchScalingGroupError(self.tenant_id, self.uuid)

        metadata = yield in_context(_get_server_metadata)
        personality = yield in_context(_get_personality)
        networks = yield in_context(_get_networks)
        load_balancers = yield in_context(_get_load_balancers)

        result = {
            "type": "launch_server",
            "args": {
                "server": dict({"metadata": metadata,
                                "personality": personality,
                                "networks": networks},
                               **server),
                "loadBalancers": load_balancers
            }
        }
        returnValue(result)

    def _check_limit(self, conn, entity_type, new, policy_id=None):
        if entity_type == "policies":
            limit_type = "maxPoliciesPerGroup"
            count_d = _count_policies(conn, self.uuid)
            e_cls = iface.PoliciesOverLimitError
            e_args = self.tenant_id, self.uuid
        elif entity_type == "webhooks":
            limit_type = "maxWebhooksPerPolicy"
            count_d = _count_webhooks(conn, policy_id)
            e_cls = iface.WebhooksOverLimitError
            e_args = self.tenant_id, self.uuid, policy_id
        else:
            raise RuntimeError("Unknown limited entity type {}"
                               .format(entity_type))

        limit_d = _get_limit(conn, self.tenant_id, limit_type)
        d = gatherResults([limit_d, count_d])

        @d.addCallback
        def check_limit(result):
            limit, current = result
            if current + new > limit:
                raise e_cls(*(e_args + (limit, current, new)))

        return d

    def modify_state(self, modifier_callable, *args, **kwargs):
        """
        See :meth:`~iface.IScalingGroup.modify_state`.
        """
        # TODO: actually implement
        raise RuntimeError("ACTUALLY IMPLEMENT THIS")

    @_with_transaction
    def create_policies(self, conn, policy_cfgs):
        """
        See :meth:`~iface.IScalingGroup.create_policies`.
        """
        d = self._check_limit(conn, "policies", len(policy_cfgs))

        @d.addCallback
        def create_policies(_result):
            ds = [_create_policy(conn, self.uuid, cfg) for cfg in policy_cfgs]
            return gatherResults(ds, consumeErrors=True)

        @d.addCallback
        def created_policies(policy_ids):
            return [dict(id=policy_id, **policy_cfg)
                    for policy_id, policy_cfg in zip(policy_ids, policy_cfgs)]

        return d.addErrback(self._check_if_group_exists_if_batch_failed)

    def _check_if_group_exists_if_batch_failed(self, f):
        """
        This bunch of deferreds failed; if it failed because of an
        integrity error, that's because the scaling group referred to
        doesn't exist. Raise the appropriate exception.

        :returns: Never.
        :raises iface.NoSuchScalingGroupError: If this is a :class:`FirstError`
            wrapping an :class:`IntegrityError`.
        :raises: The passed failure in every other case.
        """
        f.trap(FirstError)

        subFailure = f.value.subFailure
        subFailure.trap(IntegrityError)

        raise iface.NoSuchScalingGroupError(self.tenant_id, self.uuid)

    @_with_transaction
    def update_policy(self, conn, policy_id, data):
        """
        See :meth:`~iface.IScalingGroup.update_policy`.
        """
        try:
            adjustment_type = _get_adjustment_type(data)
            data["adjustment_type"] = adjustment_type
            data["adjustment_value"] = data.pop(adjustment_type)
        except KeyError:
            pass

        d = conn.execute(policies.update()
                         .where(policies.c.id == policy_id)
                         .values(**data))
        d.addCallback(self._complain_if_missing_policy, conn, policy_id)
        return d

    @_with_transaction
    def update_launch_config(self, conn, data):
        """
        See :meth:`~iface.IScalingGroup.update_launch_config`.
        """
        args = data["args"]
        server = args["server"]

        ds = []
        for table in [server_payloads, server_metadata, personalities,
                      networks, load_balancers]:
            q = table.delete().where(table.c.scaling_group_id == self.uuid)
            ds.append(conn.execute(q))
        d = gatherResults(ds)

        @d.addCallback
        def insert(result):
            ds = []

            for src, key, table in [(args, "loadBalancers", load_balancers),
                                    (server, "personality", personalities),
                                    (server, "networks", networks)]:
                values = [dict(scaling_group_id=self.uuid, **part)
                          for part in src.get(key, [])]
                if values:
                    ds.append(conn.execute(table.insert(), values))

            metadata_vals = [dict(scaling_group_id=self.uuid, key=k, value=v)
                             for k, v in server.get("metadata", {}).items()]
            if metadata_vals:
                ds.append(conn.execute(server_metadata.insert(),
                                       metadata_vals))

            payload_vals = [dict(scaling_group_id=self.uuid, key=k, value=v)
                            for k, v in server.iteritems()
                            if k not in ["metadata", "personality", "networks"]]
            if payload_vals:
                ds.append(conn.execute(server_payloads.insert(),
                                       payload_vals))

            return gatherResults(ds, consumeErrors=True)

        d.addErrback(self._check_if_group_exists_if_batch_failed)
        return d.addCallback(lambda _result: None)

    def list_policies(self, limit=100, marker=None):
        """
        See :meth:`~iface.IScalingGroup.list_policies`.
        """
        # TODO: only for this tenant & group!
        query = _paginated(policies, limit, marker)
        return self._get_policies(query)

    def get_policy(self, policy_id, version=None):
        """
        See :meth:`~iface.IScalingGroup.get_policy`.
        """
        # TODO: only for this tenant and group!
        query = policies.select().where(policies.c.id == policy_id).limit(1)
        d = self._get_policies(query)

        @d.addCallback
        def just_the_one_please(policies):
            try:
                policy, = policies
                return policy
            except ValueError:
                raise iface.NoSuchPolicyError(self.tenant_id, self.uuid,
                                              policy_id)

        return d

    @_with_transaction
    def _get_policies(self, conn, query):
        """
        Gets and appropriately formats policies given by *query*.
        """
        d = conn.execute(query).addCallback(_fetchall)

        @d.addCallback
        def _maybe_check_if_group_even_exists(policy_rows):
            """
            If there are no policies, maybe the group doesn't even exist. If
            that's the case, raise an exception instead.
            """
            if not policy_rows:
                d = self._verify_group_exists(conn)
                return d.addCallback(lambda _result: policy_rows)
            return policy_rows

        @d.addCallback
        def get_policy_args(policy_rows):
            """
            Fetches the arguments (if any) for the policies in the given
            policy rows.

            :param policy_rows: The rows for the matched policies.
            :type policy_rows: :class:`list` of SQLAlchemy row-likes

            :return: The rows that were passed in, as well as all
                policy args for the given policies.
            :rtype: deferred ``(policy_rows, args_by_policy)``
            """
            policy_ids = [r["id"] for r in policy_rows]
            d = _get_policy_args(conn, policy_ids)
            d.addCallback(lambda args_by_policy: (policy_rows, args_by_policy))
            return d

        @d.addCallback
        def format_result(result):
            policy_rows, args_by_policy = result

            policies = []
            for r in policy_rows:
                policy = {"id": r["id"],
                          "name": r["name"],
                          "type": r["type"],
                          r["adjustment_type"]: r["adjustment_value"],
                          "cooldown": r["cooldown"]}

                args = args_by_policy.get(policy["id"])
                if args is not None:
                    policy["args"] = args

                policies.append(policy)

            return policies

        return d

    @_with_transaction
    def delete_policy(self, conn, policy_id):
        """
        See :meth:`~iface.IScalingGroup.delete_policy`.
        """
        # REVIEW: Add ON DELETE CASCADE to FKey constraint?
        query = policies.delete().where(policies.c.id == policy_id)
        d = conn.execute(query)
        d.addCallback(self._complain_if_missing_policy, conn, policy_id)
        return d

    @_with_transaction
    def create_webhooks(self, conn, policy_id, data):
        """
        See :meth:`~iface.IScalingGroup.create_webhooks`.
        """
        data_with_ids = []
        metadata_by_id = {}

        for d in data:
            webhook_id = bytes(uuid4())
            capability_hash = bytes(uuid4())
            # REVIEW: I really don't like the name capability_hash

            metadata_by_id[webhook_id] = d["metadata"]
            data_with_ids.append(dict(id=webhook_id,
                                      policy_id=policy_id,
                                      capability_hash=capability_hash,
                                      **d))

        d = self._check_limit(conn, "webhooks", len(data), policy_id)

        @d.addCallback
        def insert_webhooks(_result):
            return conn.execute(webhooks.insert(), data_with_ids)

        d.addErrback(self._report_missing_foreign_policy, policy_id)

        @d.addCallback
        def insert_metadata(_result):
            # TODO: refactor this logic with the stuff that sets group
            # metadata & policy args, because it's probably the same
            meta_rows = [dict(webhook_id=webhook_id, key=key, value=value)
                         for (webhook_id, meta) in metadata_by_id.iteritems()
                         for (key, value) in meta.iteritems()]
            return conn.execute(webhook_metadata.insert(), meta_rows)

        @d.addCallback
        def format_result(_result):
            return [{"id": d["id"],
                     "name": d["name"],
                     "capability": {"hash": d["capability_hash"],
                                    "version": "1"},
                     "metadata": metadata_by_id[d["id"]]}
                    for d in data_with_ids]

        return d

    def _report_missing_foreign_policy(self, f, policy_id):
        """
        If this deferred failed because of an integrity constraint, that
        is because the policy being referred to doesn't actually
        exist. Raises the appropriate exception.

        :returns: Never.
        :raises: The original exception if this failure is not a
            :class:`IntegrityError`.
        :raises: :class:`~iface.NoSuchPolicyError` if this failure is
            a :class:`IntegrityError`.
        """
        # REVIEW: I want to make a political joke here so bad.
        f.trap(IntegrityError)
        raise iface.NoSuchPolicyError(self.tenant_id, self.uuid, policy_id)

    @_with_transaction
    def get_webhook(self, conn, policy_id, webhook_id):
        """
        See :meth:`~iface.IScalingGroup.get_webhook`.
        """
        d = conn.execute(webhooks.select(webhooks.c.id == webhook_id))
        d.addCallback(_fetchone)
        d.addCallback(self._maybe_verify_why_we_cant_find_webhook)

        @d.addCallback
        def _get_metadata(row):
            d = _get_webhook_metadata(conn, webhook_id)
            d.addCallback(lambda metadata: (row, metadata))
            return d

        @d.addCallback
        def format(result):
            row, metadata = result
            return {"id": row["id"],
                    "name": row["name"],
                    "capability": {"hash": row["capability_hash"],
                                   "version": "1"},
                    "metadata": metadata}

        return d

    @inlineCallbacks
    def _maybe_verify_why_we_cant_find_webhook(self, row):
        """
        If necessary, check why we can't find anything about this webhook.
        Checks, in order, if the groups exists, the policy exists, and
        if both of those exist, conclude it's just the webhook that
        doesn't exist.

        If a row was found, just return the row.
        """
        if row is not None:
            returnValue(row)

        yield self._verify_group_exists(conn)
        yield self._verify_policy_exists(conn, policy_id))
        raise iface.NoSuchWebhookError(self.tenant_id, self.uuid,
                                       policy_id, webhook_id)


def _verify_group_exists(conn, tenant_id, group_id):
    d = conn.execute(scaling_groups
                     .select(scaling_groups.c.id == group_id)
                     .limit(1).count())
    d.addCallback(_fetchone)
    @d.addCallback
    def raise_if_count_is_zero(row):
        if row[0] == 0:
            raise iface.NoSuchScalingGroupError(tenant_id, group_id)
    return d


def _verify_policy_exists(conn, tenant_id, group_id, policy_id):
    d = conn.execute(policies
                     .select(policies.c.id == policy_id)
                     .limit(1).count())
    d.addCallback(_fetchone)
    @d.addCallback
    def raise_if_count_is_zero(row):
        if row[0] == 0:
            raise iface.NoSuchPolicyError(tenant_id, group_id, policy_id)
    return d


def _get_policy_args(conn, policy_ids):
    """
    Gets the policy args for the given policies.

    :return: All the policy args for the given policies.
    :rtype: mapping ``{policy_id: {key: value}}``
    """
    if not policy_ids:
        return succeed({})

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


@implementer(iface.IScalingGroupCollection)
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
        See :meth:`~iface.IScalingGroupCollection.create_scaling_group`.
        """
        group_id = bytes(uuid4())
        group = SQLScalingGroup(self.engine, tenant_id, group_id)

        d = conn.execute(scaling_groups.insert()
                         .values(id=group_id,
                                 tenant_id=tenant_id,
                                 name=config["name"],
                                 cooldown=config["cooldown"],
                                 minEntities=config["minEntities"],
                                 maxEntities=config.get("maxEntities")))

        @d.addCallback
        def add_launch_config_and_policies(_result_proxy):
            launch_d = group.update_launch_config(launch)
            if policies:
                policy_d = group.create_policies(policies)
                return gatherResults([launch_d, policy_d])
            return launch_d

        @d.addCallback
        def build_response(_result):
            return {
                "id": group_id,
                "state": iface.GroupState(tenant_id=tenant_id,
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

    def list_scaling_group_states(self, log, tenant_id, limit=100, marker=None):
        """
        See :meth:`~iface.IScalingGroupCollection.list_scaling_group_states`.
        """
        query = _paginated(scaling_groups, limit, marker)
        # TODO: keep in mind that this lists all groups, not just for
        # this tenant. fix that in the test, then filter here.

        d = self.engine.execute(query).addCallback(_fetchall)

        @d.addCallback
        def format_result(rows):
            # REVIEW: clearly most of this GroupState is nonsense.
            # What part of it can and can't be?
            return [iface.GroupState(tenant_id=tenant_id,
                                     group_id=row["id"],
                                     group_name=row["name"],
                                     active={},
                                     pending=[],
                                     policy_touched=None,
                                     group_touched=None,
                                     paused=False)
                    for row in rows]

        return d

    def get_scaling_group(self, log, tenant_id, scaling_group_id):
        """
        See :meth:`~iface.IScalingGroupCollection.get_scaling_group`.
        """
        return SQLScalingGroup(self.engine, tenant_id, scaling_group_id)

    def get_counts(self, log, tenant_id):
        """
        See :meth:`~iface.IScalingGroupCollection.get_counts`.
        """
        # REVIEW: I certainly hope that the query planner knows how to
        # do this sanely. It may be easier to read, albeit with more
        # database roundtrips, to do the right thing manually.

        sg, p, wh = scaling_groups, policies, webhooks

        queries = {
            "groups": (sg.select()
                         .where(sg.c.tenant_id == tenant_id)),
            "policies": (p.select()
                           .where(exists([sg.c.id],
                                         and_((sg.c.tenant_id == tenant_id),
                                              (p.c.group_id == sg.c.id))))),
            "webhooks": (wh.select()
                           .where(exists([sg.c.id],
                                         and_((sg.c.tenant_id == tenant_id),
                                              (p.c.group_id == sg.c.id),
                                              (wh.c.policy_id == p.c.id)))))
        }

        query = select([query.count().label(name)
                        for name, query in queries.iteritems()])
        d = self.engine.execute(query).addCallback(_fetchone)
        return d.addCallback(dict)

    def webhook_info_by_hash(self, log, capability_hash):
        """
        See :meth:`~iface.IScalingGroupCollection.webhook_info_by_hash`.
        """
        query = select([scaling_groups.c.tenant_id,
                        scaling_groups.c.id,
                        policies.c.id],
                       and_(policies.c.group_id == scaling_groups.c.id,
                            webhooks.c.policy_id == policies.c.id,
                            webhooks.c.capability_hash == capability_hash))
        d = self.engine.execute(query).addCallback(_fetchone)

        @d.addCallback
        def maybe_raise(result):
            """
            Maybe there is no such webhook: if so, raise an exception.
            """
            if result is None:
                raise iface.UnrecognizedCapabilityError(capability_hash, "1")
            else:
                return result

        return d

    def health_check(self):
        """
        See :meth:`~iface.IScalingGroupCollection.health_check`.
        """
        return succeed((True, {}))


@implementer(iface.IScalingScheduleCollection)
class SQLScalingScheduleCollection(object):
    """
    A scaling schedule collection backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


@implementer(iface.IAdmin)
class SQLAdmin(object):
    """
    An admin interface backed by a SQL store.
    """
    def __init__(self, engine):
        self.engine = engine


def _create_policy(conn, group_id, policy_cfg):
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
                       Column("id", String(32),
                              nullable=False, primary_key=True),
                       Column("name", String(), nullable=False),
                       Column("tenant_id", String(), nullable=False),
                       Column("cooldown", Integer(), nullable=False),
                       Column("minEntities", Integer(), nullable=False),
                       Column("maxEntities", Integer()))

group_metadata = Table("group_metadata", metadata,
                       Column("group_id", ForeignKey("scaling_groups.id"),
                              nullable=False, primary_key=True),
                       Column("key", String(),
                              nullable=False, primary_key=True),
                       Column("value", String()))

policies = Table("policies", metadata,
                 Column("id", String(32), primary_key=True),
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
                           nullable=False, primary_key=True),
                    Column("key", String(),
                           nullable=False, primary_key=True),
                    Column("value", String(), nullable=False))

webhooks = Table("webhooks", metadata,
                 Column("id", String(), primary_key=True),
                 Column("policy_id", ForeignKey("policies.id"),
                        nullable=False),
                 Column("name", String(), nullable=False),
                 Column("capability_hash", String(), nullable=False,
                        unique=True))

webhook_metadata = Table("webhook_metadata", metadata,
                         Column("webhook_id", ForeignKey("webhooks.id"),
                                nullable=False, primary_key=True),
                         Column("key", String(),
                                nullable=False, primary_key=True),
                         Column("value", String(), nullable=False))

limit_types = "maxWebhooksPerPolicy", "maxPoliciesPerGroup"

limits = Table("limits", metadata,
               Column("tenant_id", String(), primary_key=True),
               Column("limit_type", Enum(*limit_types), primary_key=True),
               Column("value", Integer(), nullable=False))

server_payloads = Table("server_payloads", metadata,
                        Column("scaling_group_id",
                               ForeignKey("scaling_groups.id"),
                               primary_key=True),
                        Column("key", String(), primary_key=True),
                        Column("value", String(), nullable=False))

server_metadata = Table("server_metadata", metadata,
                        Column("scaling_group_id",
                               ForeignKey("scaling_groups.id"),
                               nullable=False, primary_key=True),
                        Column("key", String(),
                               nullable=False, primary_key=True),
                        Column("value", String(), nullable=False))

personalities = Table("personalities", metadata,
                      Column("scaling_group_id", ForeignKey("scaling_groups.id"),
                             nullable=False, primary_key=True),
                      Column("path", String(),
                             nullable=False, primary_key=True),
                      Column("contents", String(), nullable=False))

networks = Table("networks", metadata,
                 Column("scaling_group_id",
                        ForeignKey("scaling_groups.id"),
                        nullable=False, primary_key=True),
                 Column("uuid", String(), nullable=False, primary_key=True))

load_balancers = Table("load_balancers", metadata,
                       Column("scaling_group_id", ForeignKey("scaling_groups.id"),
                              nullable=False, primary_key=True),
                       Column("loadBalancerId", Integer(),
                              nullable=False, primary_key=True),
                       Column("port", Integer(),
                              nullable=False))


def create_tables(engine, tables=metadata.tables.values()):
    """
    Creates all the given tables on the given engine.

    :param tables: The tables to create. If unspecified, creates all tables.

    Please note that this function, by default, will only create tables that
    were defined when it was. No dynamic table creation!
    """
    return gatherResults(engine.execute(CreateTable(table))
                         for table in tables)


_fetchall = methodcaller("fetchall")
_fetchone = methodcaller("fetchone")


def _paginated(table, limit, marker):
    """
    Builds a pagination query for the items in *table*.

    If the marker is :data:`None`, starts from the start.
    """
    query = table.select().order_by(table.c.id).limit(limit)

    if marker is not None:
        query = query.where(table.c.id > marker)

    return query


def _get_pairs(table, conn, item_id, formatter):
    """
    Gets a bunch of pairs encoded in a key-value-ish schema.

    :param table: A table with a foreign key, and some data cols.
    :param conn: Current database connection.
    :param item_id: The id of the item being referenced by the single foreign
        key in the provided table.
    :param formatter: A callable that will be called with the matched rows,
        the table, and the foreign key column, and returns the formatted
        result.
    :returns: A deferred that will fire with the result of the formatter.

    """
    foreign_column = _get_foreign_key(table)
    query = table.select().where(foreign_column == item_id)
    d = conn.execute(query).addCallback(_fetchall)
    return d.addCallback(formatter, table, foreign_column)


def _format_key_value(rows, _table, _foreign_column):
    """
    Formats the given rows as a bunch of key-value pairs.

    Assumes the rows have ``key`` and ``value`` columns.
    """
    return {row["key"]: row["value"] for row in rows}


_get_metadata = partial(_get_pairs, formatter=_format_key_value)
_get_group_metadata = partial(_get_metadata, group_metadata)
_get_webhook_metadata = partial(_get_metadata, webhook_metadata)
_get_server_payload = partial(_get_metadata, server_payloads)
_get_server_metadata = partial(_get_metadata, server_metadata)


def _format_array(rows, table, foreign_column):
    """
    Formats a bunch of rows as a sequence of dicts.

    The sequence will look like this::

        [{"a": 0, "b": 1}, {"a": 2, "b": 3}, ...]

    So, a list of dicts, all with the same keys (the keys being the
    non-foreign key of the table) and respective values.

    """
    # REVIEW: this is a terrible name
    other_keys = [name for name, column in table.columns.items()
                  if column is not foreign_column]
    return [{col_name: row[col_name] for col_name in other_keys}
            for row in rows]


_get_array = partial(_get_pairs, formatter=_format_array)
_get_personality = partial(_get_array, personalities)
_get_networks = partial(_get_array, networks)
_get_load_balancers = partial(_get_array, load_balancers)


def _get_foreign_key(table):
    """
    Returns the name and column of the first foreign key in *table*.
    """
    for column in table.columns.values():
        if column.foreign_keys == table.foreign_keys:
            return column
    else:
        raise AssertionError("no foreign key in table {}".format(table))


def _get_limit(conn, tenant_id, limit_type):
    """
    Get the limit for the tenant.

    :param conn: The database connection to use.
    :param bytes tenant_id: The tenant id of the tenant to get the limit for.
    :param limit_type: The entity type to get the limit for.
    :type limit_type: one of the :data:`limit_types`
    """
    d = conn.execute(_for_tenant_and_limit_type(limits.select(),
                                                tenant_id, limit_type))
    d.addCallback(_fetchone)

    @d.addCallback
    def maybe_return_default(row):
        if row is not None:
            return row["value"]
        else:
            return config_value('limits.absolute.' + limit_type)

    return d


def _set_limit(conn, tenant_id, limit_type, value):
    """
    Sets the limit for a group id.

    :param conn: The database connection to use.
    :param bytes tenant_id: The tenant id of the tenant to set the limit for.
    :param limit_type: The entity type to set the limit for.
    :type limit_type: one of the :data:`limit_types`
    :param int value: The value to set the limit to.
    """
    d = conn.execute(limits.insert().values(tenant_id=tenant_id,
                                            limit_type=limit_type,
                                            value=value))
    @d.addErrback
    def maybe_already_has_a_limit(f):
        f.trap(IntegrityError)
        query = _for_tenant_and_limit_type(limits.update(),
                                            tenant_id, limit_type)
        return conn.execute(query.values(value=value))

    return d


def _for_tenant_and_limit_type(query, tenant_id, limit_type):
    q = query.where(and_(limits.c.tenant_id == tenant_id,
                         limits.c.limit_type == limit_type))
    return q


def _count_webhooks(conn, policy_id):
    return _count(conn, webhooks, policy_id=policy_id)


def _count_policies(conn, group_id):
    return _count(conn, policies, group_id=group_id)


def _count(conn, table, **kwargs):
    d = conn.execute(table.select()
                     .where(and_(*[getattr(table.columns, col_name) == value
                                    for (col_name, value) in kwargs.items()]))
                     .count())
    return d.addCallback(_fetchone).addCallback(lambda row: row[0])
