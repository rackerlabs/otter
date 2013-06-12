"""
Delete all the servers on the account
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteServers(AutoscaleFixture):

    """
    Test to delete servers on the account on config
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group
        """
        super(DeleteServers, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group
        """
        super(DeleteServers, cls).tearDownClass()

    def test_delete_all_servers(self):
        """
        Deletes all the servers on the account
        """
        all_servers_response = self.server_client.list_servers()
        all_servers = all_servers_response.entity
        server_id_list = []
        for each in all_servers:
            server_id_list.append(each.id)
        for each in server_id_list:
            delete_response = self.server_client.delete_server(each)
            self.assertEquals(delete_response.status_code, 204)
