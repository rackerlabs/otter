"""
System Integration tests autoscaling with lbaas
"""
from test_repo.autoscale.fixtures import ScalingGroupWebhookFixture


class AutoscaleLbaasFixture(ScalingGroupWebhookFixture):

    """
    System tests to verify lbaas integration with autoscale
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(AutoscaleLbaasFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(AutoscaleLbaasFixture, cls).tearDownClass()

    def test_add_nodes_to_existing_lbaas(self):
        """
        Add an existing lbaas to a scaling group with minentities > 0. The servers
        on the scaling group are added as nodes to the loadbalancer
        """
        pass

    def test_negative_add_nodes_to_different_accounts_lbaas(self):
        """
        Create an lbaas on diffrent account and add it in the launch config and
        verify scaling group
        """
        pass

    def test_negative_add_nodes_to_deleted_lbaas(self):
        """
        Delete an lbaas that is added to a scaling group's launch config
        and execute policy and verify
        """
        pass
