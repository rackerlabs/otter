"""
Tests for `/groups/<groupId>/servers/` endpoint
"""
from test_repo.autoscale.fixtures import ScalingGroupPolicyFixture


class ServersTests(ScalingGroupPolicyFixture):
    """
    Group servers tests
    """

    @classmethod
    def setUpClass(cls):
        """
        Create scaling group with minEntities 1 and with policy of change=1
        """
        super(ServersTests, cls).setUpClass(change=1, gc_min_entities=1)
        print 'setupClass'

    def assert_server_deleted(self, server_id):
        servers = self.get_servers_containing_given_name_on_tenant(group_id=self.group.id)
        self.assertNotIn(server_id, servers, 'Server {} not deleted'.format(server_id))

    def test_delete_removes_and_replaces(self, replace=None):
        """
        `DELETE serverId` actually deletes the server and replaces with new server
        """
        self.wait_for_expected_number_of_active_servers(self.group.id, 1)
        server_id = self.get_servers_containing_given_name_on_tenant(group_id=self.group.id)[0]
        resp = self.autoscale_client.delete_server(self.group.id, server_id, replace)
        self.assertEqual(resp.status_code, 202,
                         'Delete server status is {}. Expected 202'.format(resp.status_code))
        # Is server really deleted?
        self.assert_server_deleted(server_id)
        # New server replaced?
        self.verify_group_state(self.group.id, 1)

    def test_delete_removed_replaced_arg(self):
        """
        `DELETE serverId?replace=true` actually deletes the server and
        replaces with new server
        """
        self.test_delete_removes_and_replaces('true')

    def test_delete_removed_not_replaced(self):
        """
        `DELETE serverId?replace=false` removes the sever and does not replace it
        """
        # Spin 1 more server
        self.autoscale_client.execute_policy(self.group.id, self.policy['id'])
        self.wait_for_expected_number_of_active_servers(self.group.id, 2)
        # Delete server
        server_id = self.get_servers_containing_given_name_on_tenant(group_id=self.group.id)[0]
        resp = self.autoscale_client.delete_server(self.group.id, server_id, replace='false')
        self.assertEqual(resp.status_code, 202,
                         'Delete server status is {}. Expected 202'.format(resp.status_code))
        # Is server really deleted?
        self.assert_server_deleted(server_id)
        # New server not replaced?
        self.verify_group_state(self.group.id, 1)

    def test_delete_server_not_found(self):
        """
        `DELETE invalid_serverId` returns 404
        """
        resp = self.autoscale_client.delete_server(self.group.id, 'junk')
        self.assertEqual(resp.status_code, 404,
                         'Delete server status is {}. Expected 404'.format(resp.status_code))

    def test_delete_below_min(self):
        """
        Calling `DELETE serverId` when number of servers are at minimum returns 403
        """
        self.wait_for_expected_number_of_active_servers(self.group.id, 1)
        server_id = self.get_servers_containing_given_name_on_tenant(group_id=self.group.id)[0]
        resp = self.autoscale_client.delete_server(self.group.id, server_id, replace='false')
        self.assertEqual(resp.status_code, 403,
                         'Delete server status is {}. Expected 403'.format(resp.status_code))
        self.assertIn('CannotDeleteServerBelowMinError', resp.content)

    def test_delete_server_invalid_replace_args(self):
        """
        `DELETE serverId?replace=bad` returns 400 with InvalidQueryArgument
        """
        server_id = self.get_servers_containing_given_name_on_tenant(group_id=self.group.id)[0]
        resp = self.autoscale_client.delete_server(self.group.id, server_id, 'bad')
        self.assertEqual(resp.status_code, 400,
                         'Delete server status is {}. Expected 400'.format(resp.status_code))
        self.assertIn('InvalidQueryArgument', resp.content)
