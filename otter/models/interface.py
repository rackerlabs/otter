"""
Interface to be used by the scaling groups engine
"""

from zope.interface import Interface, Attribute


class UnrecognizedCapabilityError(Exception):
    """
    Error to be raised when a capability hash is not recognized, or does not
    exist, or has been deleted.
    """
    def __init__(self, capability_hash, capability_version):
        super(UnrecognizedCapabilityError, self).__init__(
            "Unrecognized (version {version}) capability hash {hash}".format(
                hash=capability_hash, version=capability_version))


class NoSuchScalingGroupError(Exception):
    """
    Error to be raised when attempting operations on a scaling group that
    does not exist.
    """
    def __init__(self, tenant_id, group_id):
        super(NoSuchScalingGroupError, self).__init__(
            "No such scaling group {g} for tenant {t}".format(
                t=tenant_id, g=group_id))


class NoSuchEntityError(Exception):
    """
    Error to be raised when attempting operations on an entity that does not
    exist.
    """


class NoSuchPolicyError(Exception):
    """
    Error to be raised when attempting operations on an policy that does not
    exist.
    """
    def __init__(self, tenant_id, group_id, policy_id):
        super(NoSuchPolicyError, self).__init__(
            "No such scaling policy {p} for group {g} for tenant {t}"
            .format(t=tenant_id, g=group_id, p=policy_id))


class NoSuchWebhookError(Exception):
    """
    Error to be raised when attempting operations on an webhook that does not
    exist.
    """
    def __init__(self, tenant_id, group_id, policy_id, webhook_id):
        super(NoSuchWebhookError, self).__init__(
            "No such webhook {w} for policy {p} in group {g} for tenant {t}"
            .format(t=tenant_id, g=group_id, p=policy_id, w=webhook_id))


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group - immutable.")

    def view_manifest():
        """
        The manifest contains everything required to configure this scaling:
        the config, the launch config, and all the scaling policies.

        :return: a dictionary corresponding to the JSON schema at
            :data:``otter.json_schema.model_schemas.view_manifest``
        :rtype: ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def view_config():
        """
        :return: a view of the config, as specified by
            :data:`otter.json_schema.group_schemas.config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def view_launch_config():
        """
        :return: a view of the launch config, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def view_state():
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

    def update_config(config):
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

    def update_launch_config(launch_config):
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

    def set_steady_state(steady_state):
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

    def bounce_entity(entity_id):
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

    def create_policies(data):
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

    def update_policy(policy_id, data):
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

    def list_policies():
        """
        Gets all the policies associated with particular scaling group.

        :return: a dict of the policies, as specified by
            :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def get_policy(policy_id):
        """
        Gets the specified policy on this particular scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :return: a policy, as specified by
            :data:`otter.json_schema.group_schemas.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist - this error is optional - a
            :class:`NoSuchPolicyError` can be raised instead
        """

    def delete_policy(policy_id):
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

    def list_webhooks(policy_id):
        """
        Gets all the capability URLs created for one particular scaling policy

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :return: a dict of the webhooks, as specified by
            :data:`otter.json_schema.model_schemas.webhook_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """

    def create_webhooks(policy_id, data):
        """
        Creates a new capability URL for one particular scaling policy

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :param data: a list of details of the webhook in JSON format, as
            specified by :data:`otter.json_schema.group_schemas.webhook`
        :type data: ``list``

        :return: a dict of the webhooks mapped to their ids, as specified by
            :data:`otter.json_schema.model_schemas.webhook_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with said
            ``dict``

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """

    def get_webhook(policy_id, webhook_id):
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

    def update_webhook(policy_id, webhook_id, data):
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

    def delete_webhook(policy_id, webhook_id):
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

    def execute_webhook(policy_id, webhook_id):
        """
        Identify the scaling policy (and tenant ID, group ID, etc.) associated
        with this particular capability URL hash and execute said policy.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :param webhook_id: the uuid of the webhook
        :type webhook_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`UnrecognizedCapabilityError` if the capability hash
        does not match any non-deleted policy
        """


class IScalingGroupCollection(Interface):
    """
    Collection of scaling groups
    """
    def create_scaling_group(log, tenant_id, config, launch, policies=None):
        """
        Create scaling group based on the tenant id, the configuration
        paramaters, the launch config, and optional scaling policies.

        Validation of the config, launch config, and policies should have
        already happened by this point (whether they refer to real other
        entities, that the config's ``maxEntities`` should be greater than or
        equal to ``minEntities``, etc.).

        On successful creation, of a scaling group, the minimum entities
        parameter should immediately be enforced.  Therefore, if the minimum
        is greater than zero, that number of entities should be created after
        scaling group creation.

        :param tenant_id: the tenant ID of the tenant the scaling group
            belongs to
        :type tenant_id: ``str``

        :param config: scaling group configuration options in JSON format, as
            specified by :data:`otter.json_schema.scaling_group.config`
        :type data: ``dict``

        :param launch: scaling group launch configuration options in JSON
            format, as specified by
            :data:`otter.json_schema.scaling_group.launch_config`
        :type data: ``dict``

        :param policies: list of scaling group policies, each one given as a
            JSON blob as specified by
            :data:`otter.json_schema.scaling_group.scaling_policy`
        :type data: ``list`` of ``dict``

        :return: uuid of the newly created scaling group
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with `str`
        """

    def delete_scaling_group(log, tenant_id, scaling_group_id):
        """
        Delete the scaling group

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :param scaling_group_id: the uuid of the scaling group to delete
        :type scaling_group_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if the scaling group id
            doesn't exist for this tenant id
        """

    def list_scaling_groups(log, tenant_id):
        """
        List the scaling groups for this tenant ID

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: a list of scaling groups
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            ``list`` of :class:`IScalingGroup` providers
        """

    def get_scaling_group(log, tenant_id, scaling_group_id):
        """
        Get a scaling group model

        Will return a scaling group even if the ID doesn't exist,
        but the scaling group will throw exceptions when you try to do things
        with it.

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: scaling group model object
        :rtype: :class:`IScalingGroup` provider (no
            :class:`twisted.internet.defer.Deferred`)
        """

    def execute_webhook_hash(capability_hash):
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
