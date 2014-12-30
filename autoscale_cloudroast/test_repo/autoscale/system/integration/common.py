class CommonTestUtilities(object):
    """This class implements common behavior between the LBaaS and RCv3 tests."""

    def __init__(self, server_client, autoscale_client):
        self.server_client = server_client
        self.autoscale_client = autoscale_client

    def get_ports_from_otter_launch_configs(group_id):
        """
        Returns the list of ports in the luanch configs of the group_id
        """
        launch_config = self.autoscale_client.view_launch_config(group_id).entity
        return [lb.port for lb in launch_config.loadBalancers]


    def get_ipv4_address_list_on_servers(server_ids_list):
        """
        Returns the list of private IPv4 addresses for the given list of
        servers.
        """
        network_list = []
        for each_server in server_ids_list:
            network = self.server_client.list_addresses(each_server).entity
            for each_network in network.private.addresses:
                if str(each_network.version) is '4':
                    network_list.append(each_network.addr)
        return network_list

