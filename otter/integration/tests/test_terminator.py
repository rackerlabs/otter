"""
Test terminator
"""

import json
import os

import attr

from twisted.internet.defer import gatherResults, inlineCallbacks
from twisted.trial.unittest import TestCase

from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    get_identity,
    get_resource_mapping,
    not_mimic,
    region,
    skip_if,
    sleep
)
from otter.integration.lib.utils import diagnose
from otter.util.deferredutils import retry_and_timeout
from otter.util.retry import repeating_interval, transient_errors_except
from otter.util.http import check_success


terminator_interval = float(os.environ["AS_TERMINATOR_INTERVAL"])


@skip_if(not_mimic,
         "This requires Mimic for adding customer access policy events")
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
        self.cf_cap = CFCustomerAccess(
            os.environ['AS_MIMIC_ROOT'], self.helper.treq, self.helper.pool)

    @inlineCallbacks
    def _test_group_behavior(self, tenant_id, access_event, group_behavior):
        """
        Add given customer access event and see if group behaves as per the
        given behavior
        """
        # Authenticate with given tenant
        identity = get_identity(
            username='user{}'.format(tenant_id),
            password='pwd{}'.format(tenant_id),
            pool=self.helper.pool, convergence_tenant=tenant_id)
        yield identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region)
        # create 2 groups
        group1, _ = self.helper.create_group(min_entities=1)
        group2, _ = self.helper.create_group(min_entities=1)
        yield gatherResults([
            self.helper.start_group_and_wait(group1, self.rcs),
            self.helper.start_group_and_wait(group2, self.rcs)
        ])
        # add account access feed event
        yield self.cf_cap.add_events([(self.rcs.tenant, access_event)])
        # Check if groups behave as expected
        yield retry_and_timeout(
            lambda: gatherResults(
                [group_behavior(group1), group_behavior(group2)],
                consumeErrors=True),
            terminator_interval * 2,
            can_retry=transient_errors_except(),
            next_interval=repeating_interval(2),
            deferred_description="Waiting for groups to behave")

    def test_group_suspended(self):
        """
        If terminator receives event about account being suspended, all
        its groups will be suspended
        """
        def should_not_converge(group):
            # Cannot trigger convergence
            return group.trigger_convergence(self.rcs, [403])

        return self._test_group_behavior(
            os.environ["TERMINATOR_TENANT1"], "SUSPENDED", should_not_converge)

    def test_group_deleted(self):
        """
        If terminator receives event about account being deleted, all
        its groups will be deleted
        """
        def group_deleted(group):
            return group.trigger_convergence(self.rcs, [404])

        return self._test_group_behavior(
            os.environ["TERMINATOR_TENANT2"], "TERMINATED", group_deleted)

    @inlineCallbacks
    def test_group_enabled(self):
        """
        If terminator receives event about account being activated, all
        its groups will be activated
        """
        # Suspend groups
        yield self.test_group_suspended()

        def group_active(group):
            # Can trigger convergence
            return group.trigger_convergence(self.rcs)

        # ACTIVATE them and check
        yield self._test_group_behavior(
            os.environ["TERMINATOR_TENANT3"], "ACTIVE", group_active)

    def test_tracks_prev_link(self):
        """
        Ensures that otter keeps track of previous link received when fetching
        feeds, i.e. further requests will be done to url received in earlier
        response's "previous" rel link
        """
        # TODO


@attr.s
class CFCustomerAccess(object):
    """
    Customer Access policy events
    """
    root = attr.ib()
    treq = attr.ib()
    pool = attr.ib()

    @diagnose("Mimic", "Adding CF CAP event")
    def add_events(self, events):
        """
        Add CAP events

        :param list events: List of (tenant_id, status) tuple
        :return: Deferred
        """
        d = self.treq.post(
            "{}/cloudfeeds_cap/events".format(self.root.rstrip("/")),
            json.dumps(
                {"events": [{"tenant_id": tenant_id, "status": status}
                            for tenant_id, status in events]}),
            pool=self.pool)
        return d.addCallback(check_success, [201])
