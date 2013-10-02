"""
Deletes.
"""
from cafe.drivers.unittest.decorators import tags
from test_repo.autoscale.fixtures import AutoscaleFixture
import time


class DeleteAll(AutoscaleFixture):

    """
    Get list of groups/servers on account and delete them
    """

    @tags(type='group')
    def test_delete_all_groups_on_account(self):
        """
        Delete all groups on the account
        """
        list_groups_response = self.autoscale_client.list_scaling_groups()
        list_groups = (list_groups_response.entity).groups
        for each_group in list_groups:
            self.empty_scaling_group(each_group)
            self.autoscale_client.delete_scaling_group(each_group.id)
        list_groups_again = ((self.autoscale_client.list_scaling_groups()).entity).groups
        print 'Deleting {0} groups, {1} still exist'.format(len(list_groups), len(list_groups_again))\
            if len(list_groups_again) is not 0 else "Deleted {0} groups".format(len(list_groups))

    @tags(type='servers')
    def test_delete_all_servers_on_account(self):
        """
        Deletes all servers on the account
        """
        all_servers = (self.server_client.list_servers()).entity
        server_id_list = []
        for each_server in all_servers:
            server_id_list.append(each_server.id)
        for each_server_id in server_id_list:
            self.server_client.delete_server(each_server_id)
        list_servers = (self.server_client.list_servers()).entity
        print 'Deleting {0} servers, {1} still exist'.format(len(all_servers), len(list_servers))\
            if len(list_servers) is not 0 else "Deleted {0} servers".format(len(all_servers))

    @tags(type='nodes')
    def test_delete_all_but_one_node_on_all_loadbalancers_on_the_account(self):
        """
        Deletes all nodes on load balancers except one, on the account
        """

        loadbalancer_id_list = [self.load_balancer_1, self.load_balancer_2, self.load_balancer_3]
        for each_load_balancer in loadbalancer_id_list:
            nodes = self.lbaas_client.list_nodes(each_load_balancer).entity
            node_id_list = [each_node.id for each_node in nodes]
            if len(node_id_list) is 1:
                print 'Nothing to delete. Only one node on load balancer'
            else:
                node_id_list.pop()
                for each_node_id in node_id_list:
                    end_time = time.time() + 120
                    while time.time() < end_time:
                        delete_response = self.lbaas_client.delete_node(
                            each_load_balancer, each_node_id)
                        if 'PENDING_UPDATE' in delete_response.text:
                            time.sleep(1)
                        else:
                            break
                    else:
                        print 'Tried deleting node for 2 mins but lb {0} remained in PENDING_UPDATE '
                        'state'.format(each_load_balancer)
                list_nodes = (
                    self.lbaas_client.list_nodes(each_load_balancer)).entity
                print 'Deleted {0} nodes'.format(len(node_id_list))\
                    if len(list_nodes) > 1 else 'Deleted {0} nodes one remains'.format(len(node_id_list))
