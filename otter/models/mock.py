"""
Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroup)
import zope.interface

from twisted.internet import defer


class MockScalingGroup:
    """
    Mock scaling group record

    :ivar uuid: UUID of the scaling group
    :type uuid: ``str``

    :ivar name: name of the scaling group
    :type name: ``str``

    :ivar region: region of the scaling group
    :type region: ``str``, one of ("DFW", "LON", or "ORD")

    :ivar entity_type: entity type of the scaling group
    :type entity_type: ``str``, one of ("servers")

    :ivar cooldown: Cooldown period before more entities are added, given in
        seconds - defaults to 30 if not given
    :type cooldown: ``float``

    :ivar min_entities: minimum number of entities in this scaling group -
        defaults to 0 if not given
    :type min_entities: ``int``

    :ivar max_entities: maximum number of entities in this scaling group -
        defaults to 1e9 if not given (functionally, no upper limit)
    :type max_entities: ``int``

    :ivar steady_state_entities: the desired steady state number of entities -
        defaults to 1 if not given
    :type steady_state_entities: ``int``

    :ivar metadata: extra metadata associated with this scaling group -
        defaults to no metadata
    """
    zope.interface.implements(IScalingGroup)

    def __init__(self, uuid, data):
        self.uuid = uuid
        self.name = data['name']
        self.region = data['region']
        self.entity_type = data['entity_type']
        self.cooldown = data.get('cooldown', 30)
        self.min_entities = data.get('min_entities', 0)
        self.max_entities = data.get('max_entities', 1e9)
        self.steady_state_entities = data.get('steady_state_entities', 1)
        self.metadata = data.get('metadata', {})
        self.entities = []

    def view(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        group = {
            'name': self.name,
            'region': self.region,
            'entity_type': self.entity_type,
            'cooldown': self.cooldown,
            'min_entities': self.min_entities,
            'max_entities': self.max_entities,
            'steady_state_entities': self.steady_state_entities,
            'metadata': self.metadata
        }
        return defer.succeed(group)

    def update(self, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data```

        :return: :class:`Deferred` that fires with None
        """
        self.name = data['name']
        self.region = data['region']
        self.cooldown = data['cooldown']
        self.min_entities = data['min_entities']
        self.max_entities = data['max_entities']
        self.desired_entities = data['desired_entities']
        self.metadata = data['metadata']
        return defer.succeed(0)

    def list(self):
        """
        :return: :class:`Deferred` that fires with a list of entities in the
            scaling group
        """
        return defer.succeed(self.entities)

    def delete(self, server):
        """
        Deletes a server given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        self.entities.remove(server)
        return defer.succeed(None)

    def add(self, server):
        """
        Adds the server to the group manually

        :return: :class:`Deferred` that fires with None
        """
        self.entities.append(server)
        return defer.succeed(None)


class MockScalingGroupCollection:
    """
    Mock scaling group collections
    """
    zope.interface.implements(IScalingGroupCollection)

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

        :return: :class:`Deferred` that fires with the uuid of the created
            scaling group
        """
        self.uuid += 1
        uuid = '{0}'.format(self.uuid)
        self.data[tenant][uuid] = MockScalingGroup(uuid, data)
        return defer.succeed(uuid)

    def delete_scaling_group(self, tenant, uuid):
        """
        Delete the scaling group

        :return: :class:`Deferred` that fires with None
        """
        if tenant not in self.data or uuid not in self.data[tenant]:
            return defer.fail(NoSuchScalingGroup(tenant, uuid))
        del self.data[tenant][uuid]
        return defer.succeed(None)

    def list_scaling_groups(self, tenant):
        """
        List the scaling groups

        :return: :class:`Deferred` that fires with a mapping of scaling
            group uuids to scaling groups
        :rtype: :class:`Deferred` that fires with a ``dict``
        """
        return defer.succeed(self.data[tenant])

    def get_scaling_group(self, tenant, uuid):
        """
        Get a scaling group

        :return: :class:`Deferred` that a scaling group model
        :rtype: :class:`Deferred` that fires with a :class:`IScalingGroup`
            provider
        """
        if tenant not in self.data or uuid not in self.data[tenant]:
            return defer.fail(NoSuchScalingGroup(tenant, uuid))
        return self.data[tenant][uuid]
