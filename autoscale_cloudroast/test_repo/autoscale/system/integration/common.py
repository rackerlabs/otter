"""
Common functionality between test_system_integration_rcv3.py and ..._lbaas.py.
"""


from autoscale_fixtures.behaviors import safe_hasattr


class CommonTestUtilities(object):
    """
    This class implements common behavior between the LBaaS and RCv3 tests.
    """

    def __init__(self, server_client, autoscale_client, lbaas_client):
        self.server_client = server_client
        self.autoscale_client = autoscale_client
        self.lbaas_client = lbaas_client

    def get_ports_from_otter_launch_configs(self, group_id):
        """
        Returns the list of ports in the luanch configs of the group_id
        """
        launch_config = self.autoscale_client.view_launch_config(
            group_id).entity
        return [lb.port for lb in launch_config.loadBalancers
                if safe_hasattr(lb, 'port')]

    def get_ipv4_address_list_on_servers(self, server_ids_list):
        """
        Returns the list of private IPv4 addresses for the given list of
        servers.
        """
        network_list = []
        for each_server in server_ids_list:
            network = self.server_client.list_addresses(each_server).entity
            # Since a CLB node must be on serviceNet, there should always be a
            # private address
            for each_network in network.private.addresses:
                if str(each_network.version) is '4':
                    network_list.append(each_network.addr)
        return network_list

    def get_node_list_from_lb(self, load_balancer_id):
        """Returns the list of nodes on the load balancer."""
        return self.lbaas_client.list_nodes(load_balancer_id).entity

    def verify_lbs_on_group_have_servers_as_nodes(self, asserter, group_id,
                                                  server_ids_list, *lbaas_ids):
        """
        Given the list of active server ids on the group, create a list of the
        ip address of the servers on the group,
        and compare it to the list of ip addresses got from a list node
        call for the lbaas id.
        Get list of ports of lbaas on the group and compare to the list of
        port on the lbaas id.
        (note: the test ensures the ports are distinct during group creation,
        which escapes the case this function would fail for, which is if the
        loadbalancer had a node with the port on it already, and autoscale
        failed to add node to that same port, this will not fail. This was done
        to keep it simple.)
        """
        # call nova list server, filter by ID and create ip address list
        servers_address_list = self.get_ipv4_address_list_on_servers(
            server_ids_list)

        # call otter, list launch config, create list of ports
        port_list_from_group = self.get_ports_from_otter_launch_configs(
            group_id)

        # call list node for each lbaas, create list of Ips and ports
        ports_list = []
        for each_loadbalancer in lbaas_ids:
            get_nodes_on_lb = self.get_node_list_from_lb(each_loadbalancer)
            nodes_list_on_lb = []
            for each_node in get_nodes_on_lb:
                nodes_list_on_lb.append(each_node.address)
                ports_list.append(each_node.port)
            # compare ip address lists and port lists
            for each_address in servers_address_list:
                asserter.assertTrue(each_address in nodes_list_on_lb)
        for each_port in port_list_from_group:
            asserter.assertTrue(each_port in ports_list)
