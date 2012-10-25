"""
Mock interface for the front-end scaling groups engine
"""
from otter import scaling_groups_interface
import zope.interface

from twisted.internet import defer


class MockScalingGroup:
    """
    Mock scaling group record
    """
    zope.interface.implements(scaling_groups_interface.IScalingGroup)

    def __init__(self, uuid, data):
        self.uuid = uuid
        self.name = data['name']
        self.regions = data['regions']
        self.cooldown = data['cooldown']
        self.min_servers = data['min_servers']
        self.max_servers = data['max_servers']
        self.desired_servers = data['desired_servers']
        self.metadata = data['metadata']
        self.servers = []

    def view(self):
        """
        Returns a view of the config
        """
        group = {
            'name': self.name,
            'regions': self.regions,
            'cooldown': self.cooldown,
            'min_servers': self.min_servers,
            'max_servers': self.max_servers,
            'desired_servers': self.desired_servers,
            'metadata': self.metadata
        }
        return defer.succeed(group)

    def update_scaling_group(self, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```
        """
        self.name = data['name']
        self.regions = data['regions']
        self.cooldown = data['cooldown']
        self.min_servers = data['min_servers']
        self.max_servers = data['max_servers']
        self.desired_servers = data['desired_servers']
        self.metadata = data['metadata']
        return defer.succeed(0)

    def list_servers(self):
        """
        Returns a list of servers in the scaling group
        """
        return defer.succeed(self.servers)

    def delete_server(self, server):
        """
        Deletes a server given by the server ID
        """
        self.servers.remove(server)
        return defer.succeed(0)

    def add_server(self, server):
        """
        Adds the server to the group manually
        """
        self.servers.append(server)
        return defer.succeed(0)


class MockScalingGroupCollection:
    """
    Mock scaling group collections
    """
    zope.interface.implements(scaling_groups_interface.IScalingGroupCollection)

    def __init__(self):
        """
        Init
        """
        self.data = {}
        self.uuid = 0

    def mock_add_tenant(self, tenant):
        """ Mock add a tenant """
        self.data[tenant] = {}

    def create_scaling_group(self, tenant, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```
        """
        self.uuid += 1
        uuid = '{0}'.format(self.uuid)
        self.data[tenant][uuid] = MockScalingGroup(uuid, data)
        return defer.succeed(uuid)

    def delete_scaling_group(self, tenant, id):
        """
        Delete the scaling group
        """
        del self.data[tenant][id]
        return defer.succeed(0)

    def list_scaling_groups(self, tenant):
        """
        List the scaling groups
        """
        return defer.succeed(self.data[tenant])

    def get_scaling_group(self, tenant, id):
        """
        Get a scaling group
        """
        return self.data[tenant][id]
