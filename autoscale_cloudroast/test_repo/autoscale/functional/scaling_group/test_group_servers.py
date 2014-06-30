"""
Tests for `/groups/<groupId>/servers/` endpoint
"""
from cafe.drivers.unittest.decorators import tags
from test_repo.autoscale.fixtures import AutoscaleFixture
from autoscale.behaviors import AutoscaleBehaviors

import time


class ServersTests(AutoscaleFixture):
    """
    Group servers tests
    """

    def setUp(self):
        """
        Create scaling group with minEntities 1
        """
        behavior = AutoscaleBehaviors(self.autoscale_config, self.autoscale_client)
        self.groupid = behavior.create_scaling_group_min(gc_min_entities=1).entity.id

    def tearDown(self):
        """
        Delete the group
        """
        self.autoscale_client.delete_scaling_group(self.groupid, force='true')

    def assert_server_deleted(self, server_id):
        """
        Assert if given server is still in group
        """
        tries = 10
        interval = 15
        while tries > 0:
            servers = self.get_servers_containing_given_name_on_tenant(group_id=self.groupid)
            if server_id in servers:
                tries -= 1
                time.sleep(interval)
            else:
                return
        self.fail('Server {} in group {} not deleted'.format(server_id, self.groupid))

    @tags(speed='slow')
    def test_delete_removes_and_replaces(self, replace=None):
        """
        `DELETE serverId` actually deletes the server and replaces with new server. This
        tests with optional replace argument as the same behavior can be tested with it.
        By default, replace is not provided. This test also shows that server can be
        deleted with min servers
        """
        server_id = self.wait_for_expected_number_of_active_servers(self.groupid, 1)[0]
        resp = self.autoscale_client.delete_server(self.groupid, server_id, replace)
        self.assertEqual(resp.status_code, 202,
                         'Delete server status is {}. Expected 202'.format(resp.status_code))
        # Is server really deleted?
        self.assert_server_deleted(server_id)
        # New server replaced?
        self.verify_group_state(self.groupid, 1)

    @tags(speed='slow')
    def test_delete_removed_replaced_arg(self):
        """
        `DELETE serverId?replace=true` actually deletes the server and
        replaces with new server
        """
        self.test_delete_removes_and_replaces('true')

    @tags(speed='slow')
    def test_delete_removed_not_replaced(self):
        """
        `DELETE serverId?replace=false` removes the sever and does not replace it
        """
        # Spin 1 more server
        policyid = AutoscaleBehaviors(
            self.autoscale_config, self.autoscale_client).create_policy_min(
                self.groupid, sp_change=1)['id']
        self.autoscale_client.execute_policy(self.groupid, policyid)
        # Delete 2nd server to check that any server can be deleted
        server_id = self.wait_for_expected_number_of_active_servers(self.groupid, 2)[1]
        resp = self.autoscale_client.delete_server(self.groupid, server_id, replace='false')
        self.assertEqual(resp.status_code, 202,
                         'Delete server status is {}. Expected 202'.format(resp.status_code))
        # Is server really deleted?
        self.assert_server_deleted(server_id)
        # New server not replaced?
        self.verify_group_state(self.groupid, 1)

    def test_delete_server_not_found(self):
        """
        `DELETE invalid_serverId` returns 404
        """
        resp = self.autoscale_client.delete_server(self.groupid, 'junk')
        self.assertEqual(resp.status_code, 404,
                         'Delete server status is {}. Expected 404'.format(resp.status_code))

    @tags(speed='slow')
    def test_delete_below_min(self):
        """
        Calling `DELETE serverId` when number of servers are at minimum returns 403
        """
        server_id = self.wait_for_expected_number_of_active_servers(self.groupid, 1)[0]
        resp = self.autoscale_client.delete_server(self.groupid, server_id, replace='false')
        self.assertEqual(resp.status_code, 403,
                         'Delete server status is {}. Expected 403'.format(resp.status_code))
        self.assertIn('CannotDeleteServerBelowMinError', resp.content)

    @tags(speed='slow')
    def test_delete_server_invalid_replace_args(self):
        """
        `DELETE serverId?replace=bad` returns 400 with InvalidQueryArgument
        """
        server_id = self.wait_for_expected_number_of_active_servers(self.groupid, 1)[0]
        resp = self.autoscale_client.delete_server(self.groupid, server_id, 'bad')
        self.assertEqual(resp.status_code, 400,
                         'Delete server status is {}. Expected 400'.format(resp.status_code))
        self.assertIn('InvalidQueryArgument', resp.content)
