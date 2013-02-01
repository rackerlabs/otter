"""
 Mock interface for the front-end scaling groups engine
"""
from copy import deepcopy
from collections import defaultdict
from uuid import uuid4

import zope.interface

from twisted.internet import defer

from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchEntityError,
                                    NoSuchPolicyError)
from otter.util.hashkey import generate_capability


def generate_entity_links(tenant_id, entity_ids,
                          region="dfw", entity_type="servers", api_version="2"):
    """
    :return: a mapping entity ids to some generated links for them based on
        the parameters given
    :rtype: ``dict``
    """

    link_str = 'http://{0}.{1}.api.rackspacecloud.com/v{2}/{3}/{1}'.format(
        region, entity_type, api_version, tenant_id)
    return dict([
        (entity_id,
         [{'rel': 'self', 'href': '{0}/{1}'.format(link_str, entity_id)}])
        for entity_id in entity_ids])


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
        self.active_entities = {}
        self.pending_entities = {}
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
            self.policies = {}
            if creation['policies']:
                self.create_policies(creation['policies'])
            self.webhooks = defaultdict(dict)
        else:
            self.error = NoSuchScalingGroupError(tenant_id, uuid)
            self.config = None
            self.launch = None
            self.policies = None
            self.webhooks = None

    def view_manifest(self):
        """
        The manifest contains everything required to configure this scaling:
        the config, the launch config, and all the scaling policies.

        :return: a dictionary corresponding to the JSON schema at
            :data:``otter.json_schema.model_schemas.view_manifest``
        :rtype: ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
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
        :return: a view of the config, as specified by
            :data:`otter.json_schema.group_schemas.config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.config.copy())

    def view_launch_config(self):
        """
        :return: a view of the launch config, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.launch.copy())

    def view_state(self):
        """
        The state of the scaling group consists of a mapping of entity id's to
        entity links for the current entities in the scaling group, a mapping
        of entity id's to entity links for the pending entities in the scaling
        group, the desired steady state number of entities, and a boolean
        specifying whether scaling is currently paused.

        The entity links are in JSON link format.

        :return: a view of the state of the scaling group corresponding to the
            JSON schema at :data:``otter.json_schema.model_schemas.group_state``

        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
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
        attributes in ``config``.  This can update the already-existing values,
        or just overwrite them - it is up to the implementation.

        Every time this is updated, the steady state and the number of entities
        should be checked/modified to ensure compliance with the minimum and
        maximum number of entities.

        :param config: Configuration data in JSON format, as specified by
            :data:`otter.json_schema.scaling_group.config`
        :type config: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
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
        Update the scaling group launch configuration parameters based on the
        attributes in ``launch_config``.  This can update the already-existing
        values, or just overwrite them - it is up to the implementation.

        :param launch_config: launch config data in JSON format, as specified
            by :data:`otter.json_schema.scaling_group.launch_config`
        :type launch_config: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        self.launch = data
        return defer.succeed(None)

    def set_steady_state(self, steady_state):
        """
        The steady state represents the number of entities - defaults to the
        minimum. This number represents how many entities _should_ be
        currently in the system to handle the current load. Its value is
        constrained to be between ``min_entities`` and ``max_entities``,
        inclusive.

        :param steady_state: The new value for the desired number of entities
            in steady state.  If this value is greater than ``max_entities``,
            the value will be set to ``max_entities``.  Similarly, if this
            value is less than ``min_entities``, the value will be set to
            ``min_entities``.
        :type steady_state: ``int``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
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
        Rebuilds an entity given by the entity ID.  This essentially deletes
        the given entity and a new one will be rebuilt in its place.

        :param entity_id: the uuid of the entity to delete
        :type entity_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: NoSuchEntityError if the entity is not a member of the scaling
            group
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
        Gets all the policies associated with particular scaling group.

        :return: a dict of the policies, as specified by
            :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        return defer.succeed(self.policies)

    def get_policy(self, policy_id):
        """
        Gets the specified policy on this particular scaling group.

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :return: a policy, as specified by
            :data:`otter.json_schema.scaling_group.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        if policy_id in self.policies:
            # return a coyp so this store doesn't get corrupted
            return defer.succeed(self.policies[policy_id].copy())
        else:
            return defer.fail(NoSuchPolicyError(self.tenant_id,
                                                self.uuid, policy_id))

    def create_policies(self, data):
        """
        Create a set of new scaling policies.

        :param data: a list of one or more scaling policies in JSON format,
            each of which is defined by
            :data:`otter.json_schema.group_schemas.policy`
        :type data: ``list`` of ``dict``

        :return: dictionary of UUIDs to their matching newly created scaling
            policies, as specified by
            :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: ``dict`` of ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        return_data = {}

        for policy in data:
            policy_id = str(uuid4())
            self.policies[policy_id] = policy
            return_data[policy_id] = policy

        return defer.succeed(return_data)

    def update_policy(self, policy_id, data):
        """
        Updates an existing policy with the data given.

        :param policy_id: the uuid of the entity to update
        :type policy_id: ``str``

        :param data: the details of the scaling policy in JSON format
        :type data: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        if policy_id in self.policies:
            self.policies[policy_id] = data
            return defer.succeed(None)
        else:
            return defer.fail(NoSuchPolicyError(self.tenant_id,
                                                self.uuid, policy_id))

    def delete_policy(self, policy_id):
        """
        Delete the specified policy on this particular scaling group, and all
        of its associated webhooks as well.

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        if policy_id in self.policies:
            del self.policies[policy_id]

            if policy_id in self.webhooks:
                del self.webhooks[policy_id]

            return defer.succeed(None)
        else:
            return defer.fail(NoSuchPolicyError(self.tenant_id,
                                                self.uuid, policy_id))

    def list_webhooks(self, policy_id):
        """
        Gets all the capability URLs created for one particular scaling policy

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :return: a dict of the webhooks, as specified by
            :data:`otter.json_schema.group_schemas.webhook`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        if policy_id in self.policies:
            # return a copy so this store doesn't get mutated
            return defer.succeed(deepcopy(self.webhooks.get(policy_id, {})))
        else:
            return defer.fail(NoSuchPolicyError(self.tenant_id,
                                                self.uuid, policy_id))

    def create_webhooks(self, policy_id, data):
        """
        Creates a new capability URL for one particular scaling policy

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :param data: the details of the webhook in JSON format, as specified
            by :data:`otter.json_schema.group_schemas.webhook`
        :type data: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        if self.error is not None:
            return defer.fail(self.error)

        if policy_id in self.policies:
            created = {}
            for webhook_input in data:
                webhook_real = {'metadata': {}}
                webhook_real.update(webhook_input)
                webhook_real['capability'] = {}

                (ignore, webhook_real['capability']['hash'],
                 webhook_real['capability']['version']) = generate_capability()

                uuid = str(uuid4())
                self.webhooks[policy_id][uuid] = webhook_real
                # return a copy so this store doesn't get mutated
                created[uuid] = webhook_real.copy()

            return defer.succeed(created)
        else:
            return defer.fail(NoSuchPolicyError(self.tenant_id,
                                                self.uuid, policy_id))

    def get_webhook(self, policy_id, webhook_id):
        """
        Gets the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :param webhook_id: the uuid of the webhook
        :type webhook_id: ``str``

        :return: a webhook, as specified by
            :data:`otter.json_schema.model_schemas.webhook`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        :raises: :class:`NoSuchWebhookError` if the webhook id does not exist
        """
        raise NotImplementedError()

    def update_webhook(self, policy_id, webhook_id, data):
        """
        Update the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :param webhook_id: the uuid of the webhook
        :type webhook_id: ``str``

        :param data: the details of the scaling policy in JSON format
        :type data: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        :raises: :class:`NoSuchWebhookError` if the webhook id does not exist
        """
        raise NotImplementedError()

    def delete_webhook(self, policy_id, webhook_id):
        """
        Delete the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :param webhook_id: the uuid of the webhook
        :type webhook_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        :raises: :class:`NoSuchWebhookError` if the webhook id does not exist
        """
        raise NotImplementedError()

    # ---- not interface methods
    def add_entities(self, pending=None, active=None):
        """
        Takes a list of pending entity ids and active entity ids, and adds
        them to the group's list of pending entitys and active entities,
        respectively.

        :param pending: list of pending entity ids
        :type pending: ``list`` or ``tuple``

        :param active: list of active entity ids
        :type active: ``list`` or ``tuple``
        """
        mapping = ((pending or [], self.pending_entities),
                   (active or [], self.active_entities))
        for entity_ids, dictionary in mapping:
            dictionary.update(generate_entity_links(self.tenant_id, entity_ids))


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

    def create_scaling_group(self, tenant, config, launch, policies=None):
        """
        Create the scaling group, and create config's ``minEntities`` number
        of pending entities on the scaling group.

        :return: :class:`Deferred` that fires with the uuid of the created
            scaling group
        """
        uuid = str(uuid4())
        self.data[tenant][uuid] = MockScalingGroup(
            tenant, uuid,
            {'config': config, 'launch': launch, 'policies': policies})

        self.data[tenant][uuid].add_entities(
            pending=[str(uuid4()) for i in xrange(config['minEntities'])])

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

    def execute_webhook(self, capability_hash):
        """
        Identify the scaling policy (and tenant ID, group ID, etc.) associated
        with this particular capability URL hash and execute said policy.

        :param capability_hash: the capability hash associated with a particular
            scaling policy
        :type capability_hash: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`UnrecognizedCapabilityError` if the capability hash
            does not match any non-deleted policy
        """
        raise NotImplementedError()
