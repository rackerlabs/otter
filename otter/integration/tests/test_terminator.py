"""
Test terminator
"""

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

    def test_group_suspended(self):
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
        # add account suspended access feed event
        yield self.access_policy_feeds.add_event(self.rcs.tenant, "SUSPENDED")
        # Check if group can be executed
        yield group1.trigger_convergence(self.rcs, [403])


    def test_group_deleted(self):
        """
        If terminator receives event about account being deleted, all
        its groups will be deleted
        """

    def test_group_enabled(self):
        """
        If terminator receives event about account being activated, all
        its groups will be activated
        """
