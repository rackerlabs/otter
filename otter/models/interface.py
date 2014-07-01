"""
Interface to be used by the scaling groups engine
"""
from zope.interface import Interface, Attribute

from otter.util import timestamp


class GroupState(object):
    """
    Object that represents the state

    :ivar str tenant_id: the tenant ID of the scaling group whose state this
        object represents

    :ivar str group_id: the ID of the scaling group whose state this
        object represents
    :ivar str group_name: the name of the scaling group whose state this
        object represents
    :ivar str desired: the desired capacity of the scaling group
    :ivar dict active: the mapping of active server ids and their info
    :ivar dict pending: the list of pending job ids and their info
    :ivar bool paused: whether the scaling group is paused in scaling activities
    :ivar dict policy_touched: dictionary mapping policy ids to the last time
        they were executed, if ever.
    :ivar str group_touched: timezone-aware timestamp that represents when the
        last time any policy was executed on the group.  Could be None.
    :ivar callable now: callable that returns a ``str`` timestamp - used for
        testing purposes.  Defaults to :func:`timestamp.now`

    TODO: ``remove_active``, ``pause`` and ``resume`` ?
    """
    def __init__(self, tenant_id, group_id, group_name, active, pending, group_touched,
                 policy_touched, paused, desired=0, now=timestamp.now):
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.group_name = group_name
        self.desired = desired
        self.active = active
        self.pending = pending
        self.paused = paused
        self.policy_touched = policy_touched
        self.group_touched = group_touched

        if self.group_touched is None:
            self.group_touched = timestamp.MIN

        self.now = now

        self._attributes = (
            'tenant_id', 'group_id', 'group_name', 'desired', 'active',
            'pending', 'group_touched', 'policy_touched', 'paused')

    def __eq__(self, other):
        """
        Two states are equal if all of the parameters are equal (except for
        the now callable)
        """
        return all((getattr(self, param) == getattr(other, param)
                    for param in self._attributes))

    def __ne__(self, other):
        """
        Negate __eq__
        """
        return other.__class__ != self.__class__ or not self.__eq__(other)

    def __repr__(self):
        """
        Prints out a representation of self
        """
        return "GroupState({0})".format(", ".join([
            str(getattr(self, attr)) for attr in self._attributes
        ]))

    def remove_job(self, job_id):
        """
        Removes a pending job from the pending list.  If the job is not in
        pending, raises an AssertionError.

        :param str job_id:  the id of the job to complete
        :returns: None
        :raises: :class:`AssertionError` if the job doesn't exist
        """
        assert job_id in self.pending, "Job doesn't exist: {0}".format(job_id)
        del self.pending[job_id]

    def add_job(self, job_id):
        """
        Adds a pending job to the pending collection.  If the job is already in
        pending, raises an AssertError.

        :param str job_id:  the id of the job to complete
        :returns: None
        :raises: :class:`AssertionError` if the job already exists
        """
        assert job_id not in self.pending, "Job exists: {0}".format(job_id)
        self.pending[job_id] = {'created': self.now()}

    def add_active(self, server_id, server_info):
        """
        Adds a server to the collection of active servers.  Adds a creation time
        if there isn't one.

        :param str job_id:  the id of the job to complete
        :param dict server_info: a dictionary containing relevant server info.
            TBD: What's in server_info ultimately - currently: name, url
        :returns: None
        :raises: :class:`AssertionError` if the server id already exists
        """
        assert server_id not in self.active, "Server already exists: {}".format(server_id)
        server_info.setdefault('created', self.now())
        self.active[server_id] = server_info

    def remove_active(self, server_id):
        """
        Removes a server to the collection of active servers.

        :param str server_id:  the id of the server to delete
        :raises: :class:`AssertionError` if the server id does not exist
        """
        assert server_id in self.active, "Server does not exists: {}".format(server_id)
        del self.active[server_id]

    def mark_executed(self, policy_id):
        """
        Record the execution time (now) of a particular policy.  This also
        updates the group touched time.

        :param str policy_id:  the id of the policy that was executed
        :returns: None
        """
        self.policy_touched[policy_id] = self.group_touched = self.now()

    def get_capacity(self):
        """
        :returns: a dictionary with the desired_capcity, current_capacity, and
        pending_capacity.
        """
        return {'current_capacity': len(self.active),
                'pending_capacity': len(self.pending),
                'desired_capacity': len(self.active) + len(self.pending)}


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


class GroupNotEmptyError(Exception):
    """
    Error to be raised when attempting to delete group that still has entities
    in it
    """
    def __init__(self, tenant_id, group_id):
        super(GroupNotEmptyError, self).__init__(
            "Group {g} for tenant {t} still has entities."
            .format(t=tenant_id, g=group_id))


class ScalingGroupOverLimitError(Exception):
    """
    Error to be raised when client requests new scaling group but
    is already at MaxGroups
    """
    def __init__(self, tenant_id, max_groups):
        super(ScalingGroupOverLimitError, self).__init__(
            "Allowed limit of {n} scaling groups reached by tenant {t}"
            .format(t=tenant_id, n=max_groups))


class WebhooksOverLimitError(Exception):
    """
    Error to be raised when client requests some number of new webhooks that
    would put them over maxWebhooksPerPolicy
    """
    def __init__(self, tenant_id, group_id, policy_id, max_webhooks,
                 curr_webhooks, new_webhooks):
        super(WebhooksOverLimitError, self).__init__(
            ("Currently there are {c} webhooks for tenant {t}, scaling group "
             "{g}, policy {p}.  Creating {n} new webhooks would exceed the "
             "webhook limit of {m} per policy.")
            .format(t=tenant_id, g=group_id, p=policy_id, m=max_webhooks,
                    c=curr_webhooks, n=new_webhooks))


class PoliciesOverLimitError(Exception):
    """
    Error to be raised when client requests number of new policies that
    will put them over maxPolicies
    """
    def __init__(self, tenant_id, group_id, max_policies, curr_policies,
                 new_policies):
        super(PoliciesOverLimitError, self).__init__(
            ("Currently there are {c} policies for tenant {t}, scaling group "
             "{g}. Creating {n} new policies would exceed the "
             "policy limit of {m} per group.")
            .format(t=tenant_id, g=group_id, m=max_policies,
                    c=curr_policies, n=new_policies))


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group - immutable.")
    tenant_id = Attribute("Rackspace Tenant ID of the owner of this group.")

    def view_manifest(with_webhooks=False):
        """
        The manifest contains everything required to configure this scaling:
        the config, the launch config, and all the scaling policies.

        :param with_webhooks: Should webhooks information be included?
        :type config: ``Bool``

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
        :return: the state information as a :class:`GroupState`

        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def delete_group():
        """
        Deletes the scaling group if the state is empty.  This method should
        handle its own locking, if required.

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if the scaling group id
            doesn't exist for this tenant id
        :raises: :class:`GroupNotEmptyError` if the scaling group cannot be
            deleted (e.g. if the state is not empty)
        """

    def update_config(config):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``config``.  This can update the already-existing values,
        or just overwrite them - it is up to the implementation.

        Enforcing the new min/max constraints should be done elsewhere.

        :param config: Configuration data in JSON format, as specified by
            :data:`otter.json_schema.group_schemas.config`
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
            by :data:`otter.json_schema.group_schemas.launch_config`
        :type launch_config: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def modify_state(modifier_callable, *args, **kwargs):
        """
        Updates the scaling group state, replacing the whole thing.  This
        takes a callable which produces a state, and then saves it if the
        callable successfully returns it, overwriting the entire previous state.
        This method should handle its own locking, if necessary.  If the
        callback is unsuccessful, does not save.

        :param modifier_callable: a ``callable`` that takes as first two
            arguments the :class:`IScalingGroup`, a :class:`GroupState`, and
            returns a :class:`GroupState`.  Other arguments provided to
            :func:`modify_state` will be passed to the ``callable``.

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def create_policies(data):
        """
        Create a set of new scaling policies.

        :param data: a list of one or more scaling policies in JSON format,
            each of which is defined by
            :data:`otter.json_schema.group_schemas.policy`
        :type data: ``list`` of ``dict``

        :return: list of newly created scaling policies and their ids, as
            specified by :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: ``list`` of ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        :raises: :class:`PoliciesOverLimitError` if newly created policies
            breaches maximum policies per group
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

    def list_policies(limit=100, marker=None):
        """
        Gets all the policies associated with particular scaling group.

        :param int limit: the maximum number of policies to return
            (for pagination purposes)
        :param str marker: the policy ID of the last seen policy (for
            pagination purposes - page offsets)

        :return: a list of the policies, as specified by
            :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``list``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """

    def get_policy(policy_id, version=None):
        """
        Gets the specified policy on this particular scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: ``str``

        :param version: version of policy to check as Type-1 UUID
        :type version: ``UUID``

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

    def list_webhooks(policy_id, limit=100, marker=None):
        """
        Gets all the capability URLs created for one particular scaling policy

        :param int limit: the maximum number of policies to return
            (for pagination purposes)
        :param str marker: the policy ID of the last seen policy (for
            pagination purposes - page offsets)

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :return: a list of the webhooks, as specified by
            :data:`otter.json_schema.model_schemas.webhook_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """

    def create_webhooks(policy_id, data):
        """
        Creates a new webhook URL for a scaling policy.

        :param policy_id: The UUID of the policy for which to create a
            new webhook.
        :type policy_id: ``str``

        :param data: a list of details of the webhook in JSON format, as
            specified by :data:`otter.json_schema.group_schemas.webhook`
        :type data: ``list``

        :return: a list of the webhooks with their ids, as specified by
            :data:`otter.json_schema.model_schemas.webhook_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with said
            ``list``

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        :raises: :class:`WebhooksOverLimitError` if creating all the specified
            webhooks would put the user over their limit of webhooks per policy
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


class IScalingScheduleCollection(Interface):
    """
    A list of scaling events in the future
    """

    def fetch_and_delete(bucket, now, size=100):
        """
        Fetch and delete and batch of scheduled events in a bucket

        :param bucket: bucket whose events to be fetched
        :type param: ``int``

        :param now: the current time
        :type now: ``datetime``

        :param size: the size of the request
        :type size: ``int``

        :return: Deferred that fires with list of dict representing a row
        """

    def add_cron_events(cron_events):
        """
        Add cron events equally distributed among the buckets

        :param cron_events: list of events (dict) to be added
        :type cron_events: ``list``

        :return: None
        """

    def get_oldest_event(bucket):
        """
        Get oldest event from the bucket

        :param bucket: oldest event from this bucket
        :type param: ``int``

        :return: Deferred that fires with dict of oldest event
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
            specified by :data:`otter.json_schema.group_schemas.config`
        :type data: ``dict``

        :param launch: scaling group launch configuration options in JSON
            format, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :type data: ``dict``

        :param policies: list of scaling group policies, each one given as a
            JSON blob as specified by
            :data:`otter.json_schema.group_schemas.scaling_policy`
        :type data: ``list`` of ``dict``

        :return: a dictionary corresponding to the JSON schema at
            :data:``otter.json_schema.model_schemas.view_manifest``, except that
            it also has the key `id`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with ``dict``
        """

    def list_scaling_group_states(log, tenant_id, limit=100, marker=None):
        """
        List the scaling groups states for this tenant ID

        :param tenant_id: the tenant ID of the scaling group info to list
        :type tenant_id: ``str``

        :param int limit: the maximum number of scaling group states to return
            (for pagination purposes)
        :param str marker: the group ID of the last seen group (for
            pagination purposes - page offsets)

        :return: a list of scaling group states
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            ``list`` of :class:`GroupState`
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

    def webhook_info_by_hash(log, capability_hash):
        """
        Fetch the tenant id, group id, and policy id for the webhook
        with this particular capability URL hash.

        :param capability_hash: the capability hash associated with a particular
            scaling policy
        :type capability_hash: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with
            a 3-tuple of (tenant_id, group_id, policy_id).

        :raises: :class:`UnrecognizedCapabilityError` if the capability hash
            does not match any non-deleted policy
        """

    def get_counts(log, tenant_id):
        """
        Returns total current count of policies, webhooks and groups in the
        following format::

            {
                "groups": 100,
                "policies": 100,
                "webhooks": 100
            }

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: a :class:`twisted.internet.defer.Deferred` containing current
            count of tenants policies, webhooks and groups as ``dict``
        """

    def health_check():
        """
        Check if the collection is healthy, and additionally provides some
        extra free-form health data.

        :return: The health information in the form of a boolean and some
            additional free-form health data (possibly empty).
        :rtype: :class:`tuple` of (:class:`bool`, :class:`dict`)
        """


class IAdmin(Interface):
    """
    Interface to administrative information and actions.
    """

    def get_metrics(self, log):
        """
        Returns total current count of policies, webhooks and groups in the
        following format::

            {
                "groups": 100,
                "policies": 100,
                "webhooks": 100
            }

        :return: a :class:`twisted.internet.defer.Deferred` containing current
            count of tenants policies, webhooks and groups as ``dict``
        """
