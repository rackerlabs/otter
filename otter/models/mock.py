"""
Mock (in memory) implementation of the store for the front-end scaling groups
engine
"""
from copy import deepcopy
from collections import defaultdict
from functools import partial
from uuid import uuid4

from zope.interface import implementer

from twisted.internet import defer

from otter.models.interface import (
    GroupNotEmptyError, GroupState, IScalingGroup, IScalingGroupCollection,
    NoSuchScalingGroupError, NoSuchPolicyError, NoSuchWebhookError,
    UnrecognizedCapabilityError)
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


@implementer(IScalingGroup)
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

    :ivar active_entities: the servers corresponding to the active
        entities in this scaling group, in the following format::

            {
                "instance id": {
                    "name": "sever name"
                    "instanceURL": "instance URL",
                    "created": <timestamp_of_creation>
                }, ...
            }

    :type active_entities: ``dict`` of ``dict``

    :ivar pending_jobs: the job id's corresponding to the pending
        entities in this scaling group, in the following format::

            {
                "job_id": {"created": <timestamp_of_creation>},
                ...
            }

    :type pending_jobs: ``dict`` of ``dict``

    :ivar paused: whether to allow new scaling activity (such as policy
        executions) - if ``True`` (paused), then no new activity can occur.
        If ``False`` (not paused), then scaling proceeds as normal.
    :type paused: ``bool``

    :ivar _collection: a :class:`MockScalingGroupCollection`
    """
    def __init__(self, log, tenant_id, uuid, collection, creation=None):
        """
        Creates a MockScalingGroup object.  If the actual scaling group should
        be created, a creation argument is provided containing the config, the
        launch config, and optional scaling policies.
        """
        self.log = log.bind(system=self.__class__.__name__)
        self.tenant_id = tenant_id
        self.uuid = uuid

        self.state = GroupState(self.tenant_id, self.uuid, {}, {}, None, {}, False)

        self._collection = collection

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
            'scalingPolicies': self.policies,
            'id': self.uuid
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
        return defer.succeed(self.state)

    def modify_state(self, modifier_callable):
        """
        see :meth:`otter.models.interface.IScalingGroup.modify_state`
        """
        def assign_state(new_state):
            assert (new_state.tenant_id == self.tenant_id and
                    new_state.group_id == self.uuid)
            self.state = new_state

        d = self.view_state()
        d.addCallback(partial(modifier_callable, self))
        d.addCallback(assign_state)
        return d

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

        return defer.succeed(None)

    def update_launch_config(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_launch_config`
        """
        if self.error is not None:
            return defer.fail(self.error)

        self.launch = data
        return defer.succeed(None)

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

                (webhook_real['capability']['version'],
                 webhook_real['capability']['hash']) = generate_capability()

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

    def delete_group(self):
        """
        see :meth:`otter.models.interface.IScalingGroupState.delete_group`
        """
        if self.error is not None:
            return defer.fail(self.error)

        if len(self.state.pending) + len(self.state.active) > 0:
            return defer.fail(GroupNotEmptyError(self.tenant_id, self.uuid))

        collection = self._collection
        self._collection = None  # lose this reference
        del collection.data[self.tenant_id][self.uuid]

        return defer.succeed(None)


@implementer(IScalingGroupCollection)
class MockScalingGroupCollection:
    """
    .. autointerface:: otter.models.interface.IScalingGroupCollection
    """
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
            log, tenant, uuid, self,
            {'config': config, 'launch': launch, 'policies': policies})

        return self.data[tenant][uuid].view_manifest()

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
        return result or MockScalingGroup(log, tenant, uuid, self, None)

    def webhook_info_by_hash(self, log, capability_hash):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.webhook_info_by_hash`
        """
        for tenant_id in self.data:
            for group_id in self.data[tenant_id]:
                webhooks = self.data[tenant_id][group_id].webhooks
                for policy_id in webhooks:
                    for webhook_id in webhooks[policy_id]:
                        if webhooks[policy_id][webhook_id]['capability']['hash'] == capability_hash:
                            return defer.succeed((tenant_id, group_id, policy_id))

        return defer.fail(UnrecognizedCapabilityError(capability_hash, 1))
