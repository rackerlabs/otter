def get_ports_from_otter_launch_configs(group_id):
    """
    Returns the list of ports in the luanch configs of the group_id
    """
    launch_config = self.autoscale_client.view_launch_config(group_id).entity
    return [lb.port for lb in launch_config.loadBalancers]
