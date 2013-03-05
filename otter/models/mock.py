"""
Mock (in memory) implementation of the store for the front-end scaling groups
engine
"""
from copy import deepcopy
from collections import defaultdict
from uuid import uuid4

import zope.interface

from twisted.internet import defer

from otter.models.interface import (
    IScalingGroup, IScalingGroupCollection, NoSuchScalingGroupError,
    NoSuchEntityError, NoSuchPolicyError, NoSuchWebhookError, UnrecognizedCapabilityError)
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
    .. autointerface:: otter.models.interface.IScalingGroup

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

    def __init__(self, log, tenant_id, uuid, creation=None):
        """
        Creates a MockScalingGroup object.  If the actual scaling group should
        be created, a creation argument is provided containing the config, the
        launch config, and optional scaling policies.
        """
        self.log = log.name(self.__class__.__name__)
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
        see :meth:`otter.models.interface.IScalingGroup.view_manifest`
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
        see :meth:`otter.models.interface.IScalingGroup.view_config`
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.config.copy())

    def view_launch_config(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_launch_config`
        """
        if self.error is not None:
            return defer.fail(self.error)
        return defer.succeed(self.launch.copy())

    def view_state(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_state`
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
        see :meth:`otter.models.interface.IScalingGroup.update_config`
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
        see :meth:`otter.models.interface.IScalingGroup.update_launch_config`
        """
        if self.error is not None:
            return defer.fail(self.error)

        self.launch = data
        return defer.succeed(None)

    def set_steady_state(self, steady_state):
        """
        see :meth:`otter.models.interface.IScalingGroup.set_steady_state`
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
        see :meth:`otter.models.interface.IScalingGroup.bounce_entity`
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
        see :meth:`otter.models.interface.IScalingGroup.list_policies`
        """
        if self.error is not None:
            return defer.fail(self.error)

        return defer.succeed(self.policies)

    def get_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.get_policy`
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
        see :meth:`otter.models.interface.IScalingGroup.create_policies`
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
        see :meth:`otter.models.interface.IScalingGroup.update_policy`
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
        see :meth:`otter.models.interface.IScalingGroup.delete_policy`
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

    def execute_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.execute_policy`
        """
        if not policy_id in self.policies:
            return defer.fail(NoSuchPolicyError(self.tenant_id, self.uuid,
                                                policy_id))
        return defer.succeed(None)

    def list_webhooks(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_webhooks`
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
        see :meth:`otter.models.interface.IScalingGroup.create_webhooks`
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
        see :meth:`otter.models.interface.IScalingGroup.get_webhook`
        """
        if self.error is not None:
            return defer.fail(self.error)

        if not policy_id in self.policies:
            return defer.fail(NoSuchPolicyError(self.tenant_id, self.uuid,
                                                policy_id))
        if webhook_id in self.webhooks[policy_id]:
            return defer.succeed(self.webhooks[policy_id][webhook_id].copy())
        else:
            return defer.fail(NoSuchWebhookError(self.tenant_id, self.uuid,
                                                 policy_id, webhook_id))

    def update_webhook(self, policy_id, webhook_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_webhook`
        """
        if self.error is not None:
            return defer.fail(self.error)

        if not policy_id in self.policies:
            return defer.fail(NoSuchPolicyError(self.tenant_id, self.uuid,
                                                policy_id))
        if webhook_id in self.webhooks[policy_id]:
            defaulted_data = {'metadata': {}}
            defaulted_data.update(data)
            self.webhooks[policy_id][webhook_id].update(defaulted_data)
            return defer.succeed(None)
        else:
            return defer.fail(NoSuchWebhookError(self.tenant_id, self.uuid,
                                                 policy_id, webhook_id))

    def delete_webhook(self, policy_id, webhook_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_webhook`
        """
        if self.error is not None:
            return defer.fail(self.error)

        if not policy_id in self.policies:
            return defer.fail(NoSuchPolicyError(self.tenant_id, self.uuid,
                                                policy_id))
        if webhook_id in self.webhooks[policy_id]:
            del self.webhooks[policy_id][webhook_id]
            return defer.succeed(None)
        else:
            return defer.fail(NoSuchWebhookError(self.tenant_id, self.uuid,
                                                 policy_id, webhook_id))

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
    .. autointerface:: otter.models.interface.IScalingGroupCollection
    """
    zope.interface.implements(IScalingGroupCollection)

    def __init__(self):
        """
        Init
        """
        # If all authorization passes, and the user doesn't exist in the store,
        # then they must be a valid new user.  Just create an account for them.
        self.data = defaultdict(dict)

    def create_scaling_group(self, log, tenant, config, launch, policies=None):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.create_scaling_group`
        """
        uuid = str(uuid4())
        self.data[tenant][uuid] = MockScalingGroup(
            log, tenant, uuid,
            {'config': config, 'launch': launch, 'policies': policies})

        self.data[tenant][uuid].add_entities(
            pending=[str(uuid4()) for i in xrange(config['minEntities'])])

        return defer.succeed(uuid)

    def delete_scaling_group(self, log, tenant, uuid):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.delete_scaling_group`
        """
        if (tenant not in self.data or uuid not in self.data[tenant]):
            return defer.fail(NoSuchScalingGroupError(tenant, uuid))
        del self.data[tenant][uuid]
        return defer.succeed(None)

    def list_scaling_groups(self, log, tenant):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.list_scaling_groups`
        """
        return defer.succeed(self.data.get(tenant, {}).values())

    def get_scaling_group(self, log, tenant, uuid):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.get_scaling_group`
        """
        result = self.data.get(tenant, {}).get(uuid, None)

        # if the scaling group doesn't exist, return one anyway that raises
        # a NoSuchScalingGroupError whenever its methods are called
        return result or MockScalingGroup(log, tenant, uuid, None)

    def execute_webhook_hash(self, capability_hash):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.execute_webhook_hash`
        """
        for tenant_id in self.data:
            for group_id in self.data[tenant_id]:
                webhooks = self.data[tenant_id][group_id].webhooks
                for policy_id in webhooks:
                    for webhook_id in webhooks[policy_id]:
                        if webhooks[policy_id][webhook_id]['capability']['hash'] == capability_hash:
                            return self.data[tenant_id][group_id].execute_policy(policy_id)

        return defer.fail(UnrecognizedCapabilityError(capability_hash,1))
