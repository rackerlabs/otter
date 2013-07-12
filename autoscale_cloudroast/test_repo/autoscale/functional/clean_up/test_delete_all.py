"""
Deletes.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
import unittest


@unittest.skip('for now')
class DeleteAll(AutoscaleFixture):

    """
    Get list of groups/servers on account and delete them
    """

    def test_delete_all_groups_on_account(self):
        """
        Delete all the groups on the account
        """
        list_groups_response = self.autoscale_client.list_scaling_groups()
        list_groups = list_groups_response.entity
        for each_group in list_groups:
            self.empty_scaling_group(each_group)
            self.autoscale_client.delete_scaling_group(each_group.id)
        list_groups_response = self.autoscale_client.list_scaling_groups()
        list_groups = list_groups_response.entity
        self.assertTrue(len(list_groups) is '0',
                        msg="Groups still exist on the account")

    def test_delete_all_servers_on_account(self):
        """
        Deletes all the servers on the account id
        """
        all_servers_response = self.server_client.list_servers()
        all_servers = all_servers_response.entity
        server_id_list = []
        for each in all_servers:
            server_id_list.append(each.id)
        for each in server_id_list:
            delete_response = self.server_client.delete_server(each)
            self.assertEquals(delete_response.status_code, 204)
