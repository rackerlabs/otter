"""
 Mock interface for the front-end scaling groups engine
"""
from collections import defaultdict

from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchEntityError,
                                    NoSuchPolicyError)
import zope.interface

from twisted.internet import defer


class MockScalingGroup:
    """
    Mock scaling group record

    :ivar tenant_id: the tenant ID of the scaling group - once set, should not
        be updated
    :type tenant_id: ``str``

    :ivar uuid: UUID of the scaling group - once set, cannot be updated
    :type uuid: ``str``

    :ivar config: group configuration values, as specified by
        :data:`otter.json_schema.scaling_group.config`
    :type config: ``dict``

    :ivar launch: launch configuration, as specified by
        :data:`otter.json_schema.scaling_group.config`
    :type config: ``dict``

    :ivar policies: scaling policies of the group, each of which is specified
        by :data:`otter.json_schema.scaling_group.scaling_policy`
    :type config: ``dict``

    :ivar steady: the desired steady state number of entities -
        defaults to the minimum if not given.  This how many entities the
        system thinks there should be.  It is like a variable used by
        the scaling system to keep track of how many servers there should be,
        as opposed to constants like the minimum and maximum (which constrain
        what values the ``steady_state`` can be).
    :type steady_state: ``int``

    :ivar active_entities: the entity id's corresponding to the active
        entities in this scaling group
    :type active_entities: ``list``

    :ivar pending_entities: the entity id's corresponding to the pending
        entities in this scaling group
    :type pending_entities: ``list``

    :ivar running: whether the scaling is currently running, or paused
    :type entities: ``bool``
    """
    zope.interface.implements(IScalingGroup)

    def __init__(self, tenant_id, uuid, creation=None):
        """
        Creates a MockScalingGroup object.  If the actual scaling group should
        be created, a creation argument is provided containing the config, the
        launch config, and optional scaling policies.
        """
        self.tenant_id = tenant_id
        self.uuid = uuid

        # state that may be changed
        self.steady_state = 0
        self.active_entities = []
        self.pending_entities = []
        self.paused = False

        if creation is not None:
            self.error = None
            self.config = {
                'name': "",
                'cooldown': 0,
                'minEntities': 0,
                'maxEntities': None,  # no upper limit
                'metadata': {}
            }
            self.update_config(creation['config'], partial_update=True)
            self.launch = creation['launch']
            self.policies = creation.get('policies', None) or {}
        else:
            self.error = NoSuchScalingGroupError(tenant_id, uuid)
            self.config = None
            self.launch = None
            self.policies = None

    def view_manifest(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        if self.config is None:
            return defer.fail(self.error)

        return defer.succeed({
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': self.policies
        })

    def view_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.config)

    def view_launch_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the launch config
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.launch)

    def view_state(self):
        """
        :return: :class:`Deferred` that fires with a view of the state
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed({
            'steadyState': self.steady_state,
            'active': self.active_entities,
            'pending': self.pending_entities,
            'paused': self.paused
        })

    def update_config(self, data, partial_update=False):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``data``.  Has the option to partially update the config,
        since when creating the model there could be default variables.

        :return: :class:`Deferred` that fires with None
        """
        if self.error is not None:
            return defer.fail(self.error)

        # if not partial update, just replace the whole thing
        if partial_update:
            for key in data:
                self.config[key] = data[key]
        else:
            self.config = data

        # make sure the steady state is still within bounds
        return self.set_steady_state(self.steady_state)

    def update_launch_config(self, data):
        """
        Update the launch config parameters based on the attributes in
        ``data``.  Overwrites the existing launch config.  Note - no error
        checking here happens, so it's possible to get the launch config into
        an improper state.
        """
        if self.error is not None:
            return defer.fail(self.error)

        self.launch = data
        return defer.succeed(None)

    def set_steady_state(self, steady_state):
        """
        Sets the steady state value

        :param steady_state: value to set the steady state to, but will not set
            to anything below the minimum or above the maximum
        :type steady_state: ``int``

        :return: :class:`Deferred` that fires with None
        """
        if self.error is not None:
            return defer.fail(self.error)

        self.steady_state = max(steady_state, self.config['minEntities'])
        if self.config['maxEntities'] is not None:
            self.steady_state = min(self.steady_state,
                                    self.config['maxEntities'])
        return defer.succeed(None)

    def bounce_entity(self, entity_id):
        """
        Rebuilds a entity given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        if self.error is not None:
            return defer.fail(self.error)

        if entity_id in self.active_entities:
            # don't actually do anything, since this is fake
            return defer.succeed(None)
        return defer.fail(NoSuchEntityError(
            "Scaling group {0} has no such active entity {1}".format(
                self.uuid, entity_id)))

    def list_policies(self):
        """
        :return: a list of the policies, as specified by
            :data:`otter.json_schema.scaling_group.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        if self.policies is None:
            return defer.fail(self.error)
        return defer.succeed(self.policies)

    def get_policy(self, policy_id):
        """
        :return: a policy, as specified by
            :data:`otter.json_schema.scaling_group.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        if self.policies is None:
            return defer.fail(NoSuchPolicyError(policy_id))
        if policy_id in self.policies:
            return defer.succeed(self.policies.policy_id)

    def create_policy(self, data):
        """
        Creates a new policy with the data given.

        :param data: the details of the scaling policy in JSON format
        :type data: ``str``

        :return: the UUID of the newly created scaling policy
        """
        policy_id = 1
        self.policies[policy_id] = data
        return defer.succceed(policy_id)

    def update_policy(self, policy_id, data):
        """
        Updates an existing policy with the data given.

        :param data: the details of the scaling policy in JSON format
        :type data: ``str``

        :return: a policy, as specified by
            :data:`otter.json_schema.scaling_group.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``
        """
        if policy_id in self.policies:
            self.policies[policy_id] = data
            return defer.succceed(None)
        else:
            return defer.fail(NoSuchPolicyError)

    def delete_policy(self, policy_id):
        """
        Delete the scaling policy

        :param policy_id: the ID of the policy to be deleted
        :type policy_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if policy_id in self.policies:
            del self.policies[policy_id]
            return defer.succceed(None)
        else:
            return defer.fail(NoSuchPolicyError)


class MockScalingGroupCollection:
    """
    Mock scaling group collections
    """
    zope.interface.implements(IScalingGroupCollection)

    def __init__(self):
        """
        Init
        """
        # If all authorization passes, and the user doesn't exist in the store,
        # then they must be a valid new user.  Just create an account for them.
        self.data = defaultdict(dict)
        self.uuid = 0

    def create_scaling_group(self, tenant, config, launch, policies=None):
        """
        Create the scaling group

        :return: :class:`Deferred` that fires with the uuid of the created
            scaling group
        """
        self.uuid += 1
        uuid = '{0}'.format(self.uuid)
        self.data[tenant][uuid] = MockScalingGroup(
            tenant, uuid,
            {'config': config, 'launch': launch, 'policies': policies})
        return defer.succeed(uuid)

    def delete_scaling_group(self, tenant, uuid):
        """
        Delete the scaling group

        :return: :class:`Deferred` that fires with None
        """
        if (tenant not in self.data or uuid not in self.data[tenant]):
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
        return defer.succeed(self.data.get(tenant, {}).values())

    def get_scaling_group(self, tenant, uuid):
        """
        Get a scaling group

        :return: a scaling group model
        :rtype: a :class:`IScalingGroup`
            provider
        """
        result = self.data.get(tenant, {}).get(uuid, None)

        # if the scaling group doesn't exist, return one anyway that raises
        # a NoSuchScalingGroupError whenever its methods are called
        return result or MockScalingGroup(tenant, uuid, None)
