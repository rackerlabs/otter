"""
System tests for negative groups scenarios
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class NegativeGroupFixture(AutoscaleFixture):

    """
    System tests to verify negative scaling group scenarios
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(NegativeGroupFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(NegativeGroupFixture, cls).tearDownClass()

    def test_system_delete_group_delete_all_servers(self):
        """
        Verify delete scaling group when user deletes all the servers on the group
        """
        pass

    def test_system_delete_group_delete_some_servers(self):
        """
        Verify delete scaling group when user deletes some of the servers on the group
        """
        pass

    def test_system_delete_group_other_server_actions(self):
        """
        Verify delete scaling group when user performs actions on the servers in the group
        """
        pass

    def test_system_create_delete_scaling_group_server_building_indefinitely(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_execute_policy_server_building_indefinitely(self):
        """
        Verify execute policy when servers build indefinitely
        """
        pass

    def test_system_execute_policy_one_ofthe_server_builds_indefinitely(self):
        """
        Verify execute policy when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_some_servers_error(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_all_servers_error(self):
        """
        Verify create delete scaling group when servers build indefinitely
        """
        pass

    def test_system_create_delete_scaling_group_server_rate_limit_met(self):
        """
        Verify create delete group when maximum servers allowed already exist.
        """
        pass

    def test_system_execute_policy_when_server_rate_limit_met(self):
        """
        Verify execute policy when maximum servers allowed already exist.
        """
        pass

    def test_system_create_scaling_group_account_suspended(self):
        """
        Verify create scaling group when account is suspended
        """
        pass

    def test_system_execute_policy_on_suspended_account(self):
        """
        Verify create scaling group when account is suspended
        """
        pass

    def test_system_create_scaling_group_account_closed(self):
        """
        Verify create scaling group when account is closed
        """
        pass

    def test_system_execute_policy_on_closed_account(self):
        """
        Verify create scaling group when account is closed
        """
        pass

    def test_system_delete_group_unable_to_impersonate(self):
        """
        Verify delete scaling group when impersonation fails
        """
        # AUTO - 284
        pass

    def test_system_delete_group_when_nova_down(self):
        """
        Verify delete scaling group when nova is down
        """
        pass

    def test_system_delete_group_when_lbaas_down(self):
        """
        Verify delete scaling group when lbaas is down
        """
        pass
