"""
Test terminator
"""

from twisted.internet import reactor


class TerminatorTests(TestCase):
    """
    :mod:`otter.terminator` tests
    """

    def setUp(self):
        """
        Setup medium to access services
        """
        self.helper = TestHelper(self, num_clbs=1)
        self.rcs = TestResources()
        self.identity = get_identity(pool=self.helper.pool)
        return self.identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region)

    def _test_group_behavior(self, access_event, group_behavior):
        """
        If terminator receives event about account being suspended, all
        its groups will be suspended
        """
        # create 2 groups
        group1, _ = self.helper.create_group(min_entities=1)
        group2, _ = self.helper.create_group(min_entities=1)
        yield gatherResult([
            self.helper.start_group_and_wait(group1, self.rcs),
            self.helper.start_group_and_wait(group2, self.rcs)
        ])
        # add account access feed event
        yield self.access_policy_feeds.add_event(self.rcs.tenant, access_event)
        yield sleep(reactor, 10)
        # Check if groups behave as expected
        yield gatherResult([
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
