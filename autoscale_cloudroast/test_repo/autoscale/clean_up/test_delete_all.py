"""
Deletes.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture


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
        print '{0} groups still exist on the tenant'.format(len(list_groups))

    def test_delete_all_servers_on_account(self):
        """
        Deletes all the servers on the account
        """
        all_servers_response = self.server_client.list_servers()
        all_servers = all_servers_response.entity
        server_id_list = []
        for each_server in all_servers:
            server_id_list.append(each_server.id)
        for each_server_id in server_id_list:
            delete_response = self.server_client.delete_server(each_server_id)
            if delete_response.status_code != 204:
                print 'Deleting server {0} resulted in {1}'.format(
                    each_server_id, delete_response.status_code)
