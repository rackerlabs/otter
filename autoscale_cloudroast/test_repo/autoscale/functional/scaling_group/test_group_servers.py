"""
Tests for `/groups/<groupId>/servers/` endpoint
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.tools.datagen import rand_name


class ServersTests(ScalingPolicyFixture):
    """
    Group servers tests
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group with given data.
        """
        super(ServersTests, cls).setUpClass(change=1)

     def test_delete_removes_and_replaces(self):
         """
         `DELETE serverId` actually deletes the server and replaces with new server
         """
         pass

     def test_delete_removed_not_replaced(self):
         """
         `DELETE serverId?replace=false` removes the sever and does not replace it
         """
         pass

     def test_delete_server_not_found(self):
         """
         `DELETE invalid_serverId` returns 404
         """
         pass

     def test_delete_below_min(self):
         """
         Calling `DELETE serverId` when number of servers is below min returns 403 error
         """
         pass
