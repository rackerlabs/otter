"""
Interface for the front-end scaling groups engine
"""
from zope.interface import Interface, Attribute


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group")
    name = Attribute("Name of the scaling group")
    regions = Attribute("Regions the scaling group covers")
    cooldown = Attribute("Cooldown period before more servers are added")
    min_servers = Attribute("Minimum servers")
    max_servers = Attribute("Maxmimum servers")
    desired_servers = Attribute("Steady state servers")
    metadata = Attribute("User-provided metadata")

    def view():
        """
        Returns a view of the config
        """
        pass

    def update_scaling_group(data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```
        """
        pass

    def list_servers():
        """
        Returns a list of servers in the scaling group
        """
        pass

    def delete_server(server):
        """
        Deletes a server given by the server ID
        """
        pass

    def add_server(server):
        """
        Adds the server to the group manually
        """
        pass


class IScalingGroupCollection(Interface):
    """
    Collection of scaling groups
    """
    def create_scaling_group(tenant, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```
        """
        pass

    def delete_scaling_group(tenant, id):
        """
        Delete the scaling group
        """
        pass

    def list_scaling_groups(tenant):
        """
        List the scaling groups
        """
        pass

    def get_scaling_group(tenant, id):
        """
        Get a scaling group

        Will return a scaling group even if the ID doesn't exist,
        but the scaling group will throw exceptions when you try to do things
        with it.
        """
        pass
