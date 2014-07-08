"""
Tests for a SQL-backed otter store.

This uses an in-memory SQLite database, instead of canned
responses. Canned responses would be really easy to get wrong, leading
to useless tests. Furthermore, in-memory SQLite is plenty fast to be
useful as tests.

That leaves us with a choice between using regular, blocking
SQLAlchemy APIs, or using Alchimia. Alchimia is asynchronous, so using
it means we can't really use SynchronousTestCase if we're using a real
reactor. Not using Alchimia would mean we get a blocking API (which is
probably acceptable since it's in-memory SQLite), but would further
degrade the quality of the tests: any APIs we use that work with
blocking SQLAlchemy but not alchimia would cause false positives.

In-memory SQLite has an issue. Trying to use a connection from
multiple threads closes the connection. In-memory SQLite databases
only have one connection to them: closing it gets rid of the database.
So, we can only have one thread in Alchimia's thread pool: but
Alchimia unfortunately uses the reactor thread pool.

Two possible resolutions:

- Use a fake reactor that actually runs things in a thread
  synchronously instead of deferring to a thread pool.
- Limit the reactor pool to a single thread.

This code chooses the former, because it means not having to mess with
the real reactor, while keeping the benefit of testing the alchimia
code paths.
"""

from alchimia import TWISTED_STRATEGY as STRATEGY
from functools import partial
from itertools import product
from otter.json_schema import group_examples
from otter.models import interface, sql
from otter.test.utils import FakeReactorThreads
from sqlalchemy import create_engine
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from zope.interface.verify import verifyObject


def log(*a, **kw):
    """FIXME! DO SOMETHING USEFUL HERE.

    The interfaces fail to document what they want from me.
    """


def _create_sqlite():
    reactor = FakeReactorThreads()
    return create_engine("sqlite://", reactor=reactor, strategy=STRATEGY)


class SQLiteTestMixin(object):
    """
    A test mixin that sets up an asynchronous, in-memory SQLite
    database, with some alchimia + SQLAlchemy chrome plating.
    """
    def setUp(self):
        self.engine = _create_sqlite()
        return sql.create_tables(self.engine)


class SQLScalingGroupTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling group implementation implements the
        :class:`interface.IScalingGroup` interface.
        """
        group = sql.SQLScalingGroup(self.engine, b"GROUP", b"TENANT")
        verifyObject(interface.IScalingGroup, group)

    @inlineCallbacks
    def test_create_policies_happy_case(self):
        """
        The user can create a policy.

        After it is created, the user can list the policies and see
        all of them.
        """
        group = sql.SQLScalingGroup(self.engine, b"GROUP", b"TENANT")

        policy_cfgs = group_examples.policy()
        response = yield group.create_policies(policy_cfgs)

        self.assertEqual(len(response), len(policy_cfgs))

        seen_ids = set()
        for policy, policy_cfg in zip(response, policy_cfgs):
            seen_ids.add(policy.pop("id"))
            self.assertEqual(policy, policy_cfg)

        self.assertEqual(len(seen_ids), len(policy_cfgs),
                         "policy ids must be unique")

    def test_create_policies_for_nonexistant_scaling_group(self):
        """
        When attempting to create one or more policies for a group that
        doesn't exist, an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"BOGUS_GROUP", b"TENANT")
        d = group.create_policies(group_examples.policy())
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    def test_create_policies_at_limit(self):
        """
        When attempting to create a policy, but there are already too many
        policies for this group, an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"GROUP", b"TENANT")

        # TODO: figure out a way to put us at the limit

        # Create a policy
        d = group.create_policies(group_examples.policy())
        return self.assertFailure(d, interface.PoliciesOverLimitError)

    @inlineCallbacks
    def test_list_policies_for_nonexistant_scaling_group(self):
        """
        When attempting to list policies for a group that doesn't exist,
        an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"BOGUS", b"TENANT")
        d = group.list_policies(limit=1)
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_list_zero_policies(self):
        """
        Listing policies works when there are no policies.
        """
        group = sql.SQLScalingGroup(self.engine, b"GROUP", b"TENANT")
        list_response = yield group.list_policies(limit=1)
        self.assertEqual(list_response, [])

    @inlineCallbacks
    def test_list_policies(self):
        """
        Listing policies works, as does pagination.
        """
        group = sql.SQLScalingGroup(self.engine, b"GROUP", b"TENANT")

        policy_cfgs = group_examples.policy()
        response = yield group.create_policies(policy_cfgs)

        policy_ids = sorted([p["id"] for p in response])

        list_response = yield group.list_policies(limit=1)
        self.assertEqual(list_response, [policy_cfgs[0]])

        last_id = list_response[-1]["id"]
        list_response = yield group.list_policies(limit=3, marker=last_id)
        self.assertEqual(list_response, [policy_cfgs[1:4]])

    @inlineCallbacks
    def test_create_webhook_happy_case(self):
        """
        The user can create a webhook for an extant policy.
        """
        group = sql.SQLScalingGroup(self.engine)

        # Create a policy
        policy_cfg = group_examples.policy()[0]
        res = yield group.create_policies(policy_cfg)
        policy_id = res["id"]

        res = yield group.create_webhooks(policy_id, _webhook_examples())
        raise RuntimeError("do something here")

    def test_create_webhook_for_nonexistant_policy(self):
        """
        When attempting to create a webhook for a nonexistant policy, an
        exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine)
        d = group.create_webhooks(b"BOGUS", _webhook_examples())
        return self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_create_webhook_at_limit(self):
        """
        When attempting to create a webhook for an extant policy, but there
        are already too many webhooks for that policy, an exception is
        raised.
        """
        group = sql.SQLScalingGroup(self.engine)

        # Create a policy
        policy_cfg = group_examples.policy()[0]
        res = yield group.create_policies(policy_cfg)
        policy_id = res["id"]

        # Attempt to create a webhook
        d = group.create_webhooks(policy_id, _webhook_examples())
        yield self.assertFailure(d, interface.NoSuchPolicyError)


class SQLScalingScheduleCollectionTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling schedule collection implementation implements the
        :class:`interface.IScalingScheduleCollection` interface.
        """
        sched_coll = sql.SQLScalingScheduleCollection(self.engine)
        verifyObject(interface.IScalingScheduleCollection, sched_coll)


class SQLScalingGroupCollectionTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling group collection implementation implements the
        :class:`interface.IScalingGroupCollection` interface.
        """
        group_coll = sql.SQLScalingGroupCollection(self.engine)
        verifyObject(interface.IScalingGroupCollection, group_coll)


    def test_empty_count(self):
        """
        A scaling group collection has no groups, policies or webhooks.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        d = coll.get_counts(log, "tenant")
        d.addCallback(self.assertEqual, {"groups": 0,
                                         "policies": 0,
                                         "webhooks": 0})
        return d

    @inlineCallbacks
    def test_non_empty_count(self):
        """
        Counting works correctly for a collection that isn't empty.

        It will only return items for the correct tenant. Tenants do
        not affect each other.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        group_cfg = group_examples.config()[0]
        launch_cfg = group_examples.launch_server_config()[0]

        res = yield coll.create_scaling_group(log, b"tenant",
                                              group_cfg, launch_cfg)
        group = yield coll.get_scaling_group(log, b"tenant", res["id"])

        # add some policies
        policy_cfgs = group_examples.policy()
        policies = yield group.create_policies(policy_cfgs)

        # add some webhooks for the first policy
        first_webhook_policy_id = next(policy["id"] for policy in policies
                                       if policy["type"] == "webhook")
        webhook_cfgs = _webhook_examples()
        yield group.create_webhooks(first_webhook_policy_id, webhook_cfgs)

        # add a couple of false flags for a different tenant
        res = yield coll.create_scaling_group(log, b"tenant2",
                                              group_cfg, launch_cfg)
        group = yield coll.get_scaling_group(log, b"tenant2", res["id"])

        # actually count how many tenant 1 had
        result = yield coll.get_counts(log, b"tenant")
        self.assertEqual(result, {"groups": 1,
                                  "policies": 1,
                                  "webhooks": 1})

    def test_create_scaling_group(self):
        """
        Can create a scaling group with various test configurations.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        group_cfgs = group_examples.config()
        launch_cfgs = group_examples.launch_server_config()
        policies = group_examples.policy() + [None]

        ds = []
        expected_groups = []
        for args in product(group_cfgs, launch_cfgs, policies):
            ds.append(coll.create_scaling_group(log, b"tenant", *args))

            group_cfg, launch_cfg, policy_cfg = args
            expected_groups.append({"groupConfiguration": group_cfg,
                                    "launchConfiguration": launch_cfg,
                                    "scalingPolicies": policy_cfg or []})

        d = gatherResults(ds)

        @d.addCallback
        def check_groups(groups):
            n_products = len(group_cfgs) * len(launch_cfgs) * len(policies)
            self.assertEqual(len(groups), n_products)
            self.assertEqual(len(expected_groups), n_products)

            seen_ids = set()
            for manifest, expected in zip(groups, expected_groups):
                self.assertIn("id", manifest)
                seen_ids.add(manifest.pop("id"))

                self.assertIn("state", manifest)
                manifest.pop("state")

                self.assertEqual(manifest, expected)

            self.assertEqual(len(seen_ids), n_products,
                             "group ids must be unique")

        return d

    def test_scaling_group_names_are_unique_per_tenant(self):
        """
        Scaling group names must be unique for a given tenant.

        Scaling group names do *not* have to be unique between
        tenants: tenants do not affect each other.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        group_cfg = group_examples.config()[0]
        launch_cfgs = group_examples.launch_server_config()
        launch_cfg1, launch_cfg2 = launch_cfgs[:2]

        create = partial(coll.create_scaling_group, log, config=group_cfg)
        d = create(tenant_id="tenant1", launch=launch_cfg1)

        @d.addCallback
        def try_again_with_same_name(_result):
            return create(tenant_id="tenant1", launch=launch_cfg2)

        self.assertFailure(d, KeyError)

        @d.addCallback
        def try_again_with_same_name_but_for_different_tenant(_result):
            return create(tenant_id="tenant2", launch=launch_cfg1)

        return d


class SQLAdminTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL admin interface implementation implements the
        :class:`interface.IAdmin` interface.
        """
        admin = sql.SQLAdmin(self.engine)
        verifyObject(interface.IAdmin, admin)


def _webhook_examples():
    return ({"name": "webhook 1", "metadata": {"a": "1", "b": "1"}},
            {"name": "webhook 2", "metadata": {"a": "2", "b": "2"}})
