"""
Test terminator
"""

import json

import attr

from twisted.internet.defer import gatherResults, inlineCallbacks
from twisted.trial.unittest import TestCase

from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    mimic_root,
    not_mimic,
    region,
    skip_if,
    sleep
)
from otter.integration.lib.utils import diagnose
from otter.util.http import check_success


class TerminatorTests(TestCase):
    """
    :mod:`otter.terminator` tests
    """

    def setUp(self):
        """
        Setup medium to access services
        """
        self.helper = TestHelper(self, num_clbs=0)
        self.rcs = TestResources()
        self.identity = get_identity(pool=self.helper.pool)
        self.access_policy_feeds = CFCustomerAccess(
            mimic_root, self.helper.treq, self.helper.pool)
        return self.identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region)

    @inlineCallbacks
    def _test_group_behavior(self, access_event, group_behavior):
        """
        If terminator receives event about account being suspended, all
        its groups will be suspended
        """
        # create 2 groups
        group1, _ = self.helper.create_group(min_entities=1)
        group2, _ = self.helper.create_group(min_entities=1)
        yield gatherResults([
            self.helper.start_group_and_wait(group1, self.rcs),
            self.helper.start_group_and_wait(group2, self.rcs)
        ])
        # add account access feed event
        yield self.access_policy_feeds.add_events(
            [(self.rcs.tenant, access_event)])
        yield sleep(self.helper.reactor, 10)
        # Check if groups behave as expected
        yield gatherResults([
            group_behavior(group1), group_behavior(group2)
        ])

    @skip_if(not_mimic, "This requires Mimic for suspending accounts")
    def test_group_suspended(self):
        """
        If terminator receives event about account being suspended, all
        its groups will be suspended
        """
        def should_not_converge(group):
            # Cannot trigger convergence
            return group.trigger_convergence(self.rcs, [403])

        self._test_group_behavior("SUSPENDED", should_not_converge)

    def test_group_deleted(self):
        """
        If terminator receives event about account being deleted, all
        its groups will be deleted
        """
        def group_deleted(group):
            return group.trigger_convergence(self.rcs, [404])

        self._test_group_behavior("TERMINATED", group_deleted)

    def test_group_enabled(self):
        """
        If terminator receives event about account being activated, all
        its groups will be activated
        """
        # Suspend groups
        self.test_group_suspended()

        def group_active(group):
            # Can trigger convergence
            return group.trigger_convergence(self.rcs)

        # ACTIVATE them and check
        self._test_group_behavior("ACTIVE", group_active)


@attr.s
class CFCustomerAccess(object):
    root = attr.ib()
    treq = attr.ib()
    pool = attr.ib()

    def __attrs_post_init(self):
        self.cap_root = "{}/cloudfeeds_cap".format(self.root.rsplit("/"))

    @diagnose("Mimic", "Adding CF CAP event")
    def add_events(self, events):
        d = self.treq.post(
            self.cap_root + "/events",
            json.dumps(
                {"events": [{"tenant_id": tenant_id, "status": status}
                            for tenant_id, status in events]}),
            pool=self.pool)
        return d.addCallback(check_success, [201])
