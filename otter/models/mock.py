"""
 Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchEntityError)
import zope.interface

from twisted.internet import defer


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

    def __init__(self, region, uuid, config=None, tenant_id=None):
        self.uuid = uuid
        self.region = region

        self.entities = []

        self.steady_state = 0

        if config is not None:
            self.config = {
                'name': "",
                'cooldown': 0,
                'minEntities': 0,
                'maxEntities': None,  # no upper limit
                'metadata': {}
            }
            self.update_config(config)
        else:
            self.error = NoSuchScalingGroupError(tenant_id, region, uuid)
            self.config = None

    def view_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        if self.config is None:
            return defer.fail(self.error)
        return defer.succeed(self.config)

    def view_state(self):
        """
        :return: :class:`Deferred` that fires with a view of the state
        """
        if self.config is None:
            return defer.fail(self.error)
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
        if self.config is None:
            return defer.fail(self.error)

        valid_keys = ('name', 'cooldown', 'minEntities', 'maxEntities',
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
        if self.config is None:
            return defer.fail(self.error)

        self.steady_state = max(steady_state, self.config['minEntities'])
        if self.config['maxEntities'] is not None:
            self.steady_state = min(self.steady_state,
                                    self.config['maxEntities'])
        return defer.succeed(None)

    def list_entities(self):
        """
        Lists all the entities in the scaling group

        :return: :class:`Deferred` that fires with a list of entity ids
        """
        if self.config is None:
            return defer.fail(self.error)
        return defer.succeed(self.entities)

    def bounce_entity(self, entity_id):
        """
        Rebuilds a entity given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        if self.config is None:
            return defer.fail(self.error)

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

    def create_scaling_group(self, tenant, region, config=None):
        """
        Create the scaling group

        :return: :class:`Deferred` that fires with the uuid of the created
            scaling group
        """
        self.uuid += 1
        uuid = '{0}'.format(self.uuid)
        if region not in self.data[tenant]:
            self.data[tenant][region] = {}
        self.data[tenant][region][uuid] = MockScalingGroup(region, uuid,
                                                           config or {})
        return defer.succeed(uuid)

    def delete_scaling_group(self, tenant, region, uuid):
        """
        Delete the scaling group

        :return: :class:`Deferred` that fires with None
        """
        if (tenant not in self.data or
                region not in self.data[tenant] or
                uuid not in self.data[tenant][region]):
            return defer.fail(NoSuchScalingGroupError(tenant, region, uuid))
        del self.data[tenant][region][uuid]
        if len(self.data[tenant][region]) == 0:
            del self.data[tenant][region]
        return defer.succeed(None)

    def list_scaling_groups(self, tenant, region=None):
        """
        List the scaling groups

        :return: :class:`Deferred` that fires with a mapping of scaling
            group uuids to scaling groups
        :rtype: :class:`Deferred` that fires with a ``dict``
        """
        if region is None:
            reformat = {}
            for colo in self.data[tenant]:
                reformat[colo] = self.data[tenant][colo].values()
            return defer.succeed(reformat)
        elif region in self.data[tenant]:
            return defer.succeed({region: self.data[tenant][region].values()})
        else:
            return defer.succeed({region: []})  # no scaling groups

    def get_scaling_group(self, tenant, region, uuid):
        """
        Get a scaling group

        :return: a scaling group model
        :rtype: a :class:`IScalingGroup`
            provider
        """
        result = self.data.get(tenant, {}).get(region, {}).get(uuid, None)

        # if the scaling group doesn't exist, return one anyway that raises
        # a NoSuchScalingGroupError whenever its methods are called
        return result or MockScalingGroup(region, uuid, config=None,
                                          tenant_id=tenant)
