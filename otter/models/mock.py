"""
Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchEntityError)
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

    :ivar config: mapping of config parameters to config values, as specified
        by the :data:`otter.models.interface.scaling_group_config_schema`
    :type config: ``dict``

    :ivar steady: the desired steady state number of entities -
        defaults to the minimum if not given.  This how many entities the
        system thinks there should be.  It is like a variable used by
        the scaling system to keep track of how many servers there should be,
        as opposed to constants like the minimum and maximum (which constrain
        what values the ``steady_state`` can be).
    :type steady_state: ``int``

    :ivar entities: the entity id's corresponding to the entities in this
        scaling group
    :type entities: ``list``
    """
    zope.interface.implements(IScalingGroup)

    def __init__(self, region, uuid, config=None):
        self.uuid = uuid
        self.region = region

        self.entities = []

        self.steady_state = 0
        self.config = {
            'name': "",
            'cooldown': 0,
            'min_entities': 0,
            'max_entities': None,  # no upper limit
            'metadata': {}
        }
        if config is not None:
            self.update_config(config)

    def view_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        return defer.succeed(self.config)

    def view_state(self):
        """
        :return: :class:`Deferred` that fires with a view of the state
        """
        return defer.succeed({
            'steady_state_entities': self.steady_state,
            'current_entities': len(self.entities)
        })

    def update_config(self, data):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``data``.

        :return: :class:`Deferred` that fires with None
        """
        valid_keys = ('name', 'cooldown', 'min_entities', 'max_entities',
                      'metadata')
        for key in data:
            if key in valid_keys:
                self.config[key] = data[key]

        # make sure the steady state is still within bounds
        return self.set_steady_state(self.steady_state)

    def set_steady_state(self, steady_state):
        """
        Sets the steady state value

        :param steady_state: value to set the steady state to, but will not set
            to anything below the minimum or above the maximum
        :type steady_state: ``int``

        :return: :class:`Deferred` that fires with None
        """
        self.steady_state = max(steady_state, self.config['min_entities'])
        if self.config['max_entities'] is not None:
            self.steady_state = min(self.steady_state,
                                    self.config['max_entities'])
        return defer.succeed(None)

    def list_entities(self):
        """
        Lists all the entities in the scaling group

        :return: :class:`Deferred` that fires with a list of entity ids
        """
        return defer.succeed(self.entities)

    def bounce_entity(self, entity_id):
        """
        Rebuilds a entity given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        if entity_id in self.entities:
            # don't actually do anything, since this is fake
            return defer.succeed(None)
        return defer.fail(NoSuchEntityError(
            "Scaling group {0} has no such entity {1}".format(self.uuid,
                                                              entity_id)))


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
        self.data[tenant][uuid] = MockScalingGroup(
            data['region'], uuid, data.get('config', {}))
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
