"""
System tests for launch config
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class LaunchConfigFixture(AutoscaleFixture):

    """
    System tests to verify launch config
    """

    @classmethod
    def setUpClass(cls):
        """
        Instantiate client and configs
        """
        super(LaunchConfigFixture, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(LaunchConfigFixture, cls).tearDownClass()

    def test_system_create_scaling_group_invalid_imageid(self):
        """
        Verify execute policy with invalid server image id
        """
        pass

    def test_system_scaling_group_invalid_lbaasid(self):
        """
        Verify execute policy with invalid lbaas id
        """
        pass

    def test_system_scaling_group_lbaas_draining_disabled(self):
        """
        Verify execute policy with lbaas draining or disabled
        """
        pass

    def test_system_update_launchconfig_while_group_building(self):
        """
        Verify group when launch config is updated while policy is executing.
        """
        pass

    def test_system_update_launchconfig_multiple_times(self):
        """
        Verify execute policies with multiple updates to launch config.
        """
        pass

    def test_system_update_launchconfig_to_invalid_imageid_execute_policy(self):
        """
        Verify execute policy when launch config is updated to be invalid
        """
        pass
