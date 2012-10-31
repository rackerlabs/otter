"""
Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError,
                                    InvalidEntityError, NoSuchEntityError)
import zope.interface

from twisted.internet import defer


def is_entity_id_valid(entity_id):
    """
    Whether the entity id is a valid entity id.

    :return: True if the entity is valid, False else
    """
    return isinstance(entity_id, str)


class MockScalingGroup:
    """
    Mock scaling group record

    :ivar uuid: UUID of the scaling group - once set, cannot be updated
    :type uuid: ``str``

    :ivar region: region of the scaling group
    :type region: ``str``, one of ("DFW", "LON", or "ORD")

    :ivar entity_type: entity type of the scaling group
    :type entity_type: ``str``, one of ("servers")

    :ivar name: name of the scaling group
    :type name: ``str``

    :ivar cooldown: Cooldown period before more entities are added, given in
        seconds - defaults to 0 if not given
    :type cooldown: ``float``

    :ivar min_entities: minimum number of entities in this scaling group -
        defaults to 0 if not given
    :type min_entities: ``int``

    :ivar max_entities: maximum number of entities in this scaling group -
        defaults to 1e9 if not given (functionally, no upper limit)
    :type max_entities: ``int``

    :ivar steady_state_entities: the desired steady state number of entities -
        defaults to the minimum if not given.  This how many entities the
        system thinks there should be.  It is like a variable used by
        the scaling system to keep track of how many servers there should be,
        as opposed to constants like the minimum and maximum (which constrain
        what values the ``steady_state_entities`` can be).
    :type steady_state_entities: ``int``

    :ivar metadata: extra metadata associated with this scaling group -
        defaults to no metadata
    :type metadata: ``dict``
    """
    zope.interface.implements(IScalingGroup)

    def _update_from_dict(self, data):
        """
        Updates self from a dictionary.
        """
        keys = ('name', 'entity_type', 'region', 'cooldown', 'min_entities',
                'max_entities', 'steady_state_entities', 'metatdata')
        for key in data:
            if key in keys:
                setattr(self, key, data[key])

    def __init__(self, uuid, data):
        self.uuid = uuid
        self.region = self.entity_type = None
        self.name = self.cooldown = self.min_entities = None
        self.max_entities = self.steady_state_entities = self.metadata = None
        self._update_from_dict(data)
        self.entities = []

    def view(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        group = {
            'name': self.name or "",
            'region': self.region,
            'entity_type': self.entity_type,
            'cooldown': self.cooldown or 0,
            'min_entities': self.min_entities or 0,
            'max_entities': self.max_entities or int(1e9),
            'steady_state_entities': self.steady_state_entities or 0,
            'metadata': self.metadata or {}
        }
        return defer.succeed(group)

    def update(self, data):
        """
        Update the scaling group paramaters based on the attributes
        in ``data``.

        :return: :class:`Deferred` that fires with None
        """
        self._update_from_dict(data)
        return defer.succeed(None)

    def list(self):
        """
        Lists all the entities in the scaling group

        :return: :class:`Deferred` that fires with a list of entity ids
        """
        return defer.succeed(self.entities)

    def delete(self, entity_id):
        """
        Deletes a entity given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        if entity_id in self.entities:
            self.entities.remove(entity_id)
            return defer.succeed(None)
        return defer.fail(NoSuchEntityError(
            "Scaling group {0} has no such entity {1}".format(self.uuid,
                                                              entity_id)))

    def add(self, entity_id):
        """
        Adds the entity to the group manually

        :return: :class:`Deferred` that fires with None
        """
        if is_entity_id_valid(entity_id):
            self.entities.append(entity_id)
            return defer.succeed(None)
        return defer.fail(
            InvalidEntityError("{0} is not a valid entity".format(entity_id)))


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
            return defer.fail(NoSuchScalingGroupError(tenant, uuid))
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
            return defer.fail(NoSuchScalingGroupError(tenant, uuid))
        return self.data[tenant][uuid]
