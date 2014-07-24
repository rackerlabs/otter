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
from copy import deepcopy
from itertools import product
from otter.json_schema import group_examples, model_schemas, validate
from otter.models import interface, sql
from otter.test.utils import FakeReactorThreads
from otter.util.config import set_config_data
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from twisted.internet.defer import gatherResults
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from zope.interface.verify import verifyObject


def log(*a, **kw):
    """FIXME! DO SOMETHING USEFUL HERE.

    The interfaces fail to document what they want from me.
    """


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _create_sqlite():
    reactor = FakeReactorThreads()
    return create_engine("sqlite://", reactor=reactor, strategy=STRATEGY)


class SQLiteTestMixin(object):
    """
    A test mixin that sets up an asynchronous, in-memory SQLite
    database, with some alchimia + SQLAlchemy chrome plating.
    """
    @inlineCallbacks
    def setUp(self):
        self.engine = _create_sqlite()
        yield self.engine
        yield sql.create_tables(self.engine)


class ConfigTestMixin(object):
    """
    A test mixin that sets some configuration values for every test.
    """
    def setUp(self):
        set_config_data({'limits': {'absolute': {'maxWebhooksPerPolicy': 10,
                                                 'maxPoliciesPerGroup': 10}}})
        self.addCleanup(set_config_data, {})


class SQLScalingGroupTests(SQLiteTestMixin, ConfigTestMixin, TestCase):
    def setUp(self):
        TestCase.setUp(self)
        SQLiteTestMixin.setUp(self)
        ConfigTestMixin.setUp(self)

    def _create_group(self, tenant_id=b"TENANT", policies=None):
        """Creates a group within a test collection.

        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        cfg = self._config = group_examples.config()[0]
        launch = self._launch = group_examples.launch_server_config()[0]
        d = coll.create_scaling_group(log, tenant_id, cfg, launch, policies)

        d.addCallback(lambda r: coll.get_scaling_group(log, tenant_id, r["id"]))
        return d

    def _create_policies(self, group, n=None):
        """
        Creates *n* (default: all) example policies for the group.
        """
        policy_cfgs = group_examples.policy()
        if n is not None:
            assert n <= len(policy_cfgs)
            policy_cfgs = policy_cfgs[:n]
        self._policy_cfgs = policy_cfgs
        return group.create_policies(policy_cfgs)

    def test_interface(self):
        """
        The SQL scaling group implementation implements the
        :class:`interface.IScalingGroup` interface.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"GROUP")
        verifyObject(interface.IScalingGroup, group)

    test_interface.todo = "interface not fully implemented yet"

    @inlineCallbacks
    def test_view_manifest(self):
        """
        Viewing an entire manifest works correctly.
        """
        group = yield self._create_group()
        policies = yield self._create_policies(group, n=2)

        other_group = yield self._create_group(tenant_id=b"OTHER_TENANT")
        yield self._create_policies(other_group)

        manifest = yield group.view_manifest()
        self.assertEqual(manifest["groupConfiguration"],
                         {'cooldown': 30,
                          'maxEntities': None,
                          'metadata': {},
                          'minEntities': 1,
                          'name': u'webheads'})

        self.assertIn("state", manifest)
        self.assertIn("id", manifest)

        launch = manifest["launchConfiguration"]
        self.assertEqual(launch["args"]["loadBalancers"],
                         [{'loadBalancerId': 2200, 'port': 8081}])
        self.assertEqual(launch["args"]["server"],
                         {u'OS-DCF:diskConfig': u'AUTO',
                          u'flavorRef': u'3',
                          u'imageRef': u'0d589460-f177-4b0f-81c1-8ab8903ac7d8',
                          'metadata': {u'mykey': u'myvalue'},
                          u'name': u'webhead',
                          'networks': [{'uuid': u'11111111-1111-1111-1111-111111111111'}],
                          'personality': [
                              {'contents': u'ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp',
                               'path': u'/root/.ssh/authorized_keys'}]})

        policies = manifest["scalingPolicies"]

        for policy in policies:
            policy_without_id = dict((key, value) for (key, value)
                                     in policy.iteritems() if key != "id")
            self.assertIn(policy_without_id, self._policy_cfgs)

    def test_view_config_for_nonexistent_group(self):
        """
        When attempting to view the configuration for a group that doesn't
        doesn't exist, an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS")
        d = group.view_config()
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_view_config_happy_case(self):
        """
        Viewing a config works correctly.
        """
        group = yield self._create_group()

        cfg = yield group.view_config()
        metadata = cfg.pop("metadata", {})

        expected_cfg = dict(self._config)
        expected_cfg.setdefault("maxEntities", None)
        expected_metadata = expected_cfg.pop("metadata", {})

        self.assertEqual(cfg, expected_cfg)
        self.assertEqual(metadata, expected_metadata)

    def test_view_launch_config_for_nonexistent_group(self):
        """
        When attempting to view the launch configuration for a group that
        doesn't exist, an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS")
        d = group.view_launch_config()
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_view_launch_config_happy_case(self):
        """
        Viewing a launch config works correctly.
        """
        group = yield self._create_group()
        launch_cfg = yield group.view_launch_config()
        self.assertEqual(launch_cfg, self._launch)

    def test_update_launch_config_for_nonexistent_group(self):
        """
        When attempting to update the launch configuration for a group that
        doesn't exist, an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS")
        launch = group_examples.launch_server_config()[0]
        d = group.update_launch_config(launch)
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_update_launch_config_happy_case(self):
        """
        Updating a launch config works.
        """
        group = yield self._create_group()

        old_launch_cfg = yield group.view_launch_config()
        self.assertEqual(old_launch_cfg, self._launch)

        new_launch_cfg = deepcopy(old_launch_cfg)
        old_flavor = old_launch_cfg["args"]["server"]["flavorRef"]
        new_flavor = unicode(int(old_flavor) + 1)
        new_launch_cfg["args"]["server"]["flavorRef"] = new_flavor

        yield group.update_launch_config(deepcopy(new_launch_cfg))
        got_launch_cfg = yield group.view_launch_config()
        self.assertEqual(got_launch_cfg, new_launch_cfg)

    @inlineCallbacks
    def test_create_policies_happy_case(self):
        """
        The user can create a policy.

        After it is created, the user can list the policies and see
        all of them.
        """
        group = yield self._create_group()

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
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = self._create_policies(group)

        self.assertFailure(d, interface.NoSuchScalingGroupError)

        @d.addCallback
        def exception_has_correct_message(exception):
            msg = "No such scaling group BOGUS_GROUP for tenant TENANT"
            self.assertEqual(exception.message, msg)

        return d

    @inlineCallbacks
    def test_create_policies_at_limit(self):
        """
        When attempting to create a policy, but there are already too many
        policies for this group, an exception is raised.
        """
        group = yield self._create_group()

        yield sql._set_limit(self.engine, group.tenant_id,
                             "maxPoliciesPerGroup", 1)

        yield self._create_policies(group, n=1)

        d = self._create_policies(group)
        yield self.assertFailure(d, interface.PoliciesOverLimitError)

    def test_update_policy_for_nonexistant_scaling_group(self):
        """
        When attempting to update a policy for a group that doesn't exist,
        an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = group.update_policy(b"BOGUS_POLICY", {"change": 300})
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_update_policy_for_nonexistant_policy(self):
        """
        When attempting to update a policy when that policy doesn't exist,
        an exception is raised.
        """
        group = yield self._create_group()
        d = group.update_policy(b"BOGUS_POLICY", {"change": 300})
        yield self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_update_policy(self):
        """
        A user can update a policy.
        """
        group = yield self._create_group()

        policy, = yield self._create_policies(group, n=1)

        old = yield group.get_policy(policy["id"])
        new = {"change": old["change"] * 2,
               "cooldown": old["cooldown"] * 2,
               "name": "times two",
               "type": "webhook"}
        self.assertNotEqual(old, new)

        yield group.update_policy(policy["id"], dict(new))
        got = yield group.get_policy(policy["id"])
        matched_keys = new.viewkeys() & got.viewkeys()
        self.assertEqual(len(matched_keys), len(new))
        for key in matched_keys:
            self.assertEqual(new[key], got[key])

    def test_list_policies_for_nonexistant_scaling_group(self):
        """
        When attempting to list policies for a group that doesn't exist,
        an exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = group.list_policies(limit=1)
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_list_zero_policies(self):
        """
        Listing policies works when there are no policies.
        """
        group = yield self._create_group()
        list_response = yield group.list_policies(limit=1)
        self.assertEqual(list_response, [])

    @inlineCallbacks
    def test_list_policies(self):
        """
        Listing policies works, as does pagination.
        """
        group = yield self._create_group()

        policies = yield self._create_policies(group)
        policies.sort(key=lambda policy: policy["id"])

        list_response = yield group.list_policies(limit=1)
        self.assertEqual(list_response, policies[:1])

        last_id = list_response[-1]["id"]
        list_response = yield group.list_policies(limit=3, marker=last_id)
        self.assertEqual(list_response, policies[1:4])

    def test_get_policy_for_nonexistent_group(self):
        """
        When attempting to get a policy for a group that doesn't exist, an
        exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")

        d = group.get_policy(b"SOME_POLICY")

        validExceptions = (interface.NoSuchScalingGroupError,
                           interface.NoSuchPolicyError)
        return self.assertFailure(d, *validExceptions)

    @inlineCallbacks
    def test_get_policy_for_nonexistent_policy(self):
        """
        When attempting to get a policy and that policy doesn't exist, an
        exception is raised.
        """
        group = yield self._create_group()
        d = group.get_policy(b"BOGUS_POLICY")
        yield self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_get_policy(self):
        """
        Getting a policy works.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)
        got_policy = yield group.get_policy(policy["id"])
        self.assertEqual(policy, got_policy)

    def test_delete_policy_for_nonexistent_group(self):
        """
        When attempting to delete a policy for a group that doesn't exist, an
        exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = group.delete_policy(b"POLICY")
        self.assertFailure(d, interface.NoSuchScalingGroupError)
        return d

    @inlineCallbacks
    def test_delete_nonexistant_policy(self):
        """
        When attempting to delete a policy and that policy doesn't exist, an
        exception is raised.
        """
        group = yield self._create_group()
        d = group.delete_policy(b"POLICY")
        yield self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_delete_policy(self):
        """
        Deleting a policy works.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)

        yield group.get_policy(policy["id"])
        yield group.delete_policy(policy["id"])
        d = group.get_policy(policy["id"])
        yield self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_create_webhooks_happy_case(self):
        """
        The user can create a webhook for an extant policy.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)

        webhook_cfgs = _webhook_examples()
        webhooks = yield group.create_webhooks(policy["id"], webhook_cfgs)

        # Webhooks have different ids and capability hashes:
        for getter in [lambda x: x["id"], lambda x: x["capability"]["hash"]]:
            attrs = map(getter, webhooks)
            self.assertEqual(len(attrs), len(set(attrs)))

        # Webhooks have a capability version that is always "1":
        for webhook in webhooks:
            self.assertEqual(webhook["capability"]["version"], "1")

        # Webhooks have their expected name and metadata from the config:
        for key in ["name", "metadata"]:
            for webhook, cfg in zip(webhooks, webhook_cfgs):
                self.assertEqual(webhook[key], cfg[key])

        # Check against the schema for good measure:
        validate(webhooks, model_schemas.webhook_list)

    @inlineCallbacks
    def test_create_webhooks_for_nonexistant_policy(self):
        """
        When attempting to create a webhook for a nonexistant policy, an
        exception is raised.
        """
        group = yield self._create_group()
        d = group.create_webhooks(b"BOGUS", _webhook_examples())
        yield self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_create_webhooks_at_limit(self):
        """
        When attempting to create a webhook for an extant policy, but there
        are already too many webhooks for that policy, an exception is
        raised.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)

        yield sql._set_limit(self.engine, group.tenant_id,
                             "maxWebhooksPerPolicy", 1)

        yield group.create_webhooks(policy["id"], [_webhook_examples()[0]])

        # Attempt to create a webhook
        d = group.create_webhooks(policy["id"], _webhook_examples()[1:])
        yield self.assertFailure(d, interface.WebhooksOverLimitError)

    def test_get_webhook_for_nonexistant_scaling_group(self):
        """
        When attempting to get a webhook for a nonexistant group, an
        exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = group.get_webhook(b"BOGUS_POLICY", b"BOGUS_WEBHOOK")
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    def test_get_webhook_for_nonexistant_policy(self):
        """
        When attempting to get a webhook for a nonexistant policy, an
        exception is raised.
        """
        d = self._create_group()
        d.addCallback(lambda g: g.get_webhook(b"BOGUS_POLICY", b"BOGUS_WEBHOOK"))
        return self.assertFailure(d, interface.NoSuchPolicyError)

    @inlineCallbacks
    def test_get_webhook_for_nonexistant_webhook(self):
        """
        When attempting to get a webhook that doesn't exist, an exception
        is raised.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)
        d = group.get_webhook(policy["id"], b"BOGUS_WEBHOOK")
        yield self.assertFailure(d, interface.NoSuchWebhookError)

    @inlineCallbacks
    def test_get_webhook_happy_case(self):
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)
        webhook_cfgs = [_webhook_examples()[0]]
        webhook, = yield group.create_webhooks(policy["id"], webhook_cfgs)

        got_webhook = yield group.get_webhook(policy["id"], webhook["id"])
        self.assertEqual(webhook, got_webhook)

    def test_delete_webhook_for_nonexistant_scaling_group(self):
        """
        When attempting to delete a webhook for a nonexistant group, an
        exception is raised.
        """
        group = sql.SQLScalingGroup(self.engine, b"TENANT", b"BOGUS_GROUP")
        d = group.delete_webhook(b"BOGUS_POLICY", b"BOGUS_WEBHOOK")
        return self.assertFailure(d, interface.NoSuchScalingGroupError)

    @inlineCallbacks
    def test_delete_webhook_happy_case(self):
        """
        Deleting a webhook works.
        """
        group = yield self._create_group()
        policy, = yield self._create_policies(group, n=1)
        webhook_cfgs = [_webhook_examples()[0]]
        webhook, = yield group.create_webhooks(policy["id"], webhook_cfgs)

        yield group.get_webhook(policy["id"], webhook["id"])

        yield group.delete_webhook(policy["id"], webhook["id"])
        d = group.get_webhook(policy["id"], webhook["id"])
        yield self.assertFailure(d, interface.NoSuchWebhookError)


class SQLScalingScheduleCollectionTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling schedule collection implementation implements the
        :class:`interface.IScalingScheduleCollection` interface.
        """
        sched_coll = sql.SQLScalingScheduleCollection(self.engine)
        verifyObject(interface.IScalingScheduleCollection, sched_coll)

    test_interface.todo = "interface not fully implemented yet"


class SQLScalingGroupCollectionTests(ConfigTestMixin, SQLiteTestMixin, TestCase):
    def setUp(self):
        TestCase.setUp(self)
        ConfigTestMixin.setUp(self)
        SQLiteTestMixin.setUp(self)
        self.collection = sql.SQLScalingGroupCollection(self.engine)

    @inlineCallbacks
    def _create_group(self, tenant_id=b"TENANT"):
        config = group_examples.config()[0]
        launch = group_examples.launch_server_config()[0]
        res = yield self.collection.create_scaling_group(log, tenant_id,
                                                         config, launch)
        group = self.collection.get_scaling_group(log, tenant_id, res["id"])
        returnValue(group)

    @inlineCallbacks
    def _create_some_groups(self, tenant_id=b"TENANT"):
        configs = group_examples.config()
        launch_cfgs = group_examples.launch_server_config()

        groups = []
        for config, launch in zip(configs, launch_cfgs):
            res = yield self.collection.create_scaling_group(log, tenant_id,
                                                             config, launch)
            group = self.collection.get_scaling_group(log, tenant_id, res["id"])
            groups.append(group)

        returnValue(groups)

    def test_interface(self):
        """
        The SQL scaling group collection implementation implements the
        :class:`interface.IScalingGroupCollection` interface.
        """
        verifyObject(interface.IScalingGroupCollection, self.collection)

    def test_empty_count(self):
        """
        A scaling group collection has no groups, policies or webhooks.
        """
        d = self.collection.get_counts(log, "tenant")
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
        # create a scaling group
        group = yield self._create_group()

        # add some policies
        policy_cfgs = group_examples.policy()
        policies = yield group.create_policies(policy_cfgs)

        # add some webhooks for the first policy
        first_webhook_policy_id = next(policy["id"] for policy in policies
                                       if policy["type"] == "webhook")
        webhook_cfgs = _webhook_examples()
        yield group.create_webhooks(first_webhook_policy_id, webhook_cfgs)

        # add a couple of false flags for a different tenant
        self._create_group(tenant_id=b"TENANT2")

        # actually count how many tenant 1 had
        result = yield self.collection.get_counts(log, group.tenant_id)
        self.assertEqual(result, {"groups": 1,
                                  "policies": len(policy_cfgs),
                                  "webhooks": len(webhook_cfgs)})

    def test_create_scaling_group(self):
        """
        Can create a scaling group with various test configurations.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)

        group_cfgs = group_examples.config()
        launch_cfgs = group_examples.launch_server_config()

        policies = group_examples.policy()
        policy_collections = [[policies[0]], policies[1:], None]

        ds = []
        expected_groups = []
        for args in product(group_cfgs, launch_cfgs, policy_collections):
            ds.append(coll.create_scaling_group(log, b"tenant", *args))

            group_cfg, launch_cfg, policy_cfgs = args
            expected_groups.append({"groupConfiguration": group_cfg,
                                    "launchConfiguration": launch_cfg,
                                    "scalingPolicies": policy_cfgs or []})

        d = gatherResults(ds)

        @d.addCallback
        def check_groups(groups):
            n = len(group_cfgs) * len(launch_cfgs) * len(policy_collections)
            self.assertEqual(len(groups), n)
            self.assertEqual(len(expected_groups), n)

            seen_ids = set()
            for manifest, expected in zip(groups, expected_groups):
                self.assertIn("id", manifest)
                seen_ids.add(manifest.pop("id"))

                self.assertIn("state", manifest)
                manifest.pop("state")

                self.assertEqual(manifest, expected)

            self.assertEqual(len(seen_ids), n, "group ids must be unique")

        return d

    def test_get_scaling_group(self):
        """
        Scaling groups are created with the collection's engine and the
        correct identifiers.
        """
        coll = sql.SQLScalingGroupCollection(self.engine)
        group = coll.get_scaling_group(log, b"TENANT", b"GROUP")
        self.assertEqual(group.uuid, b"GROUP")
        self.assertEqual(group.tenant_id, b"TENANT")
        self.assertEqual(group.engine, coll.engine)

    @inlineCallbacks
    def test_webhook_info_by_hash_happy_case(self):
        """
        Getting the webhook info by capability hash works.
        """
        group = yield self._create_group()

        # Set up a policy
        # TODO: refactor creating a policy
        policy_cfgs = group_examples.policy()
        response = yield group.create_policies([policy_cfgs[0]])
        policy_id = response[0]["id"]

        # Set up a webhook for the policy
        # TODO: refactor creating a webhook
        webhook_cfg = _webhook_examples()[0]
        response = yield group.create_webhooks(policy_id, [webhook_cfg])
        capa_hash = response[0]["capability"]["hash"]

        # Try to get the webhook back
        response = yield self.collection.webhook_info_by_hash(log, capa_hash)
        self.assertEqual(response, (group.tenant_id, group.uuid, policy_id))

    def test_webhook_info_by_hash_for_nonexistent_webhook(self):
        """
        Trying to find the webhook info for a nonexistent capability hash
        causes an exception.
        """
        d = self.collection.webhook_info_by_hash(log, b"BOGUS")
        self.assertFailure(d, interface.UnrecognizedCapabilityError)
        return d

    def test_list_scaling_group_states_empty(self):
        """
        Getting scaling group states works when there are no scaling groups.
        """
        d = self.collection.list_scaling_group_states(log, b"BOGUS")
        d.addCallback(self.assertEqual, [])
        return d

    @inlineCallbacks
    def test_scaling_group_states(self):
        """
        Getting scaling group states works when there are lots of scaling
        groups.
        """
        groups = yield self._create_some_groups()
        groups.sort(key=lambda g: g.uuid)
        # TODO: add some false flags

        tenant_id = groups[0].tenant_id
        itergroups = iter(groups)

        list_states = self.collection.list_scaling_group_states

        first_amount = 1
        states = yield list_states(log, tenant_id, limit=first_amount)

        def _assertStateCorrect(state, group):
            # REVIEW: lots of the state here isn't being checked. What
            # do we actually care about?
            self.assertEqual(state.tenant_id, tenant_id)
            self.assertEqual(state.group_id, group.uuid)

        self.assertEqual(len(states), first_amount)
        for state, group in zip(states, itergroups):
            _assertStateCorrect(state, group)

        marker = states[-1].group_id
        second_amount = 100
        states = yield list_states(log, tenant_id, second_amount, marker)

        remaining_groups = len(groups) - first_amount
        self.assertTrue(second_amount >= remaining_groups)

        self.assertEqual(len(states), remaining_groups)
        for state, group in zip(states, itergroups):
            _assertStateCorrect(state, group)

    def test_health_check(self):
        """
        The scaling group collection provides health info.
        """
        d = self.collection.health_check()

        @d.addCallback
        def check_response(result):
            healthy, _extra = result
            self.assertTrue(healthy)

        return d


class SQLAdminTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL admin interface implementation implements the
        :class:`interface.IAdmin` interface.
        """
        admin = sql.SQLAdmin(self.engine)
        verifyObject(interface.IAdmin, admin)

    test_interface.todo = "interface not fully implemented yet"


def _webhook_examples():
    return ({"name": "webhook 1", "metadata": {"a": "1", "b": "1"}},
            {"name": "webhook 2", "metadata": {"a": "2", "b": "2"}})

# REVIEW: is a webhook without metadata property allowed? if so add
# some examples because I'm pretty sure the code doesn't handle that

# REVIEW: Should these examples live here?
