"""
Delete resources created during tests which may not have been cleaned up.
"""
import json

from cafe.drivers.unittest.decorators import tags
from test_repo.autoscale.fixtures import AutoscaleFixture


class DeleteAll(AutoscaleFixture):
    """
    Get list of groups/servers on account and delete them.
    """

    @tags(type='group')
    def test_delete_all_groups_on_account(self):
        """
        Delete all groups on the account.
        """
        list_groups_response = self.autoscale_client.list_scaling_groups()
        list_groups = (list_groups_response.entity).groups
        for each_group in list_groups:
            self.empty_scaling_group(each_group)
            self.autoscale_client.delete_scaling_group(each_group.id)
        list_groups_again = (
            (self.autoscale_client.list_scaling_groups()).entity).groups
        if len(list_groups_again) is not 0:
            print ('Deleting {0} groups, {1} still exist'
                   .format(len(list_groups), len(list_groups_again)))
        else:
            print 'Deleted {0} groups'.format(len(list_groups))

    @tags(type='servers')
    def test_delete_all_servers_on_account(self):
        """
        Deletes all servers on the account.
        """
        all_servers = (self.server_client.list_servers()).entity
        server_id_list = []
        for each_server in all_servers:
            server_id_list.append(each_server.id)
        for each_server_id in server_id_list:
            self.server_client.delete_server(each_server_id)
        list_servers = (self.server_client.list_servers()).entity

        if len(list_servers) is not 0:
            print ('Deleting {0} servers, {1} still exist'
                   .format(len(all_servers), len(list_servers)))
        else:
            print 'Deleted {0} servers'.format(len(all_servers))

    @tags(type='loadbalancers')
    def test_delete_all_test_loadbalancers(self):
        """
        Deletes all load balancers on the account named 'test', which are
        created by these tests.
        """
        lb_response = self.lbaas_client.request('GET', self.lbaas_client.url)
        lbs = json.loads(lb_response.content).get('loadBalancers', ())
        lbs_named_test = [lb for lb in lbs if lb['name'] == 'test']

        for lb in lbs_named_test:
            self.lbaas_client.delete_load_balancer(lb['id'])
