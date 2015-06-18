"""
Interface to be used by the scaling groups engine
"""
from datetime import datetime

from croniter import croniter

from twisted.python.constants import NamedConstant, Names

from zope.interface import Attribute, Interface

from otter.util import timestamp


class GroupState(object):
    """
    Object that represents the state

    :ivar bytes tenant_id: the tenant ID of the scaling group whose state this
        object represents

    :ivar bytes group_id: the ID of the scaling group whose state this
        object represents
    :ivar bytes group_name: the name of the scaling group whose state this
        object represents
    :ivar dict active: the mapping of active server ids and their info
    :ivar dict pending: the list of pending job ids and their info
    :ivar bytes group_touched: timezone-aware ISO860 formatted timestamp
        that represents when the last time any policy was executed
        on the group. Could be None.
    :ivar dict policy_touched: dictionary mapping policy ids to the last time
        they were executed, if ever. The time is stored as ISO860 format str
    :ivar bool paused: whether the scaling group is paused in
        scaling activities
    :ivar GroupStatus status: status of the group.
    :ivar int desired: the desired capacity of the scaling group
    :ivar callable now: callable that returns a :class:`bytes` timestamp
        used for testing purposes. Defaults to :func:`timestamp.now`

    TODO: ``remove_active``, ``pause`` and ``resume`` ?
    """
    def __init__(self, tenant_id, group_id, group_name, active, pending,
                 group_touched, policy_touched, paused, status, desired=0,
                 now=timestamp.now):
        self.tenant_id = tenant_id
        self.group_id = group_id
        self.group_name = group_name
        self.desired = desired
        self.active = active
        self.pending = pending
        self.paused = paused
        self.policy_touched = policy_touched
        self.group_touched = group_touched
        self.status = status

        if self.group_touched is None:
            self.group_touched = timestamp.MIN

        self.now = now

        self._attributes = (
            'tenant_id', 'group_id', 'group_name', 'desired', 'active',
            'pending', 'group_touched', 'policy_touched', 'paused', 'status')

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
            bytes(getattr(self, attr)) for attr in self._attributes
        ]))

    def remove_job(self, job_id):
        """
        Removes a pending job from the pending list.  If the job is not in
        pending, raises an AssertionError.

        :param bytes job_id:  the id of the job to complete
        :returns: :data:`None`
        :raises AssertionError: if the job doesn't exist
        """
        assert job_id in self.pending, "Job doesn't exist: {0}".format(job_id)
        del self.pending[job_id]

    def add_job(self, job_id):
        """
        Adds a pending job to the pending collection.  If the job is already in
        pending, raises an AssertError.

        :param bytes job_id:  the id of the job to complete
        :returns: :data:`None`
        :raises AssertionError: if the job already exists
        """
        assert job_id not in self.pending, "Job exists: {0}".format(job_id)
        self.pending[job_id] = {'created': self.now()}

    def add_active(self, server_id, server_info):
        """
        Adds a server to the collection of active servers.  Adds a creation time
        if there isn't one.

        :param bytes job_id:  the id of the job to complete
        :param dict server_info: a dictionary containing relevant server info.
            TBD: What's in server_info ultimately - currently: name, url
        :returns: :data:`None`
        :raises AssertionError: if the server id already exists
        """
        assert server_id not in self.active, "Server already exists: {}".format(server_id)
        server_info.setdefault('created', self.now())
        self.active[server_id] = server_info

    def remove_active(self, server_id):
        """
        Removes a server to the collection of active servers.

        :param bytes server_id:  the id of the server to delete
        :raises AssertionError: if the server id does not exist
        """
        assert server_id in self.active, "Server does not exist: {}".format(server_id)
        del self.active[server_id]

    def mark_executed(self, policy_id):
        """
        Record the execution time (now) of a particular policy.  This also
        updates the group touched time.

        :param bytes policy_id:  the id of the policy that was executed
        :returns: :data:`None`
        """
        self.policy_touched[policy_id] = self.group_touched = self.now()

    def get_capacity(self):
        """
        Get the capacities for a group.

        :return: A dictionary with the desired_capcity, current_capacity, and
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


class ScalingGroupStatus(Names):
    """
    Status of scaling group
    """

    ACTIVE = NamedConstant()
    "Group is active and executing policies/converging"

    ERROR = NamedConstant()
    """
    Group has errored due to (mostly) invalid launch configuration and has
    stopped executing policies/converging
    """

    DELETING = NamedConstant()
    """
    Group is getting deleted and all it's resources servers/CLBs
    are getting deleted
    """


class IScalingGroup(Interface):
    """
    Scaling group record
    """
    uuid = Attribute("UUID of the scaling group - immutable.")
    tenant_id = Attribute("Rackspace Tenant ID of the owner of this group.")

    def view_manifest(with_policies=True, with_webhooks=False,
                      get_deleting=False):
        """
        The manifest contains everything required to configure this scaling:
        the config, the launch config, and all the scaling policies.

        :param bool with_policies: Should policies information be included?
        :param bool with_webhooks: If policies are included, should webhooks
            information be included?
        :param bool get_deleting: Should group be returned if it is deleting?
            If True, then returned manifest will contain "status" that will be
            one of "ACTIVE", "ERROR" or "DELETING"

        :return: a dictionary corresponding to the JSON schema at
            :data:`otter.json_schema.model_schemas.manifest`
        :rtype: :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def view_config():
        """
        :return: a view of the config, as specified by
            :data:`otter.json_schema.group_schemas.config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def view_launch_config():
        """
        :return: a view of the launch config, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def view_state():
        """
        :return: the state information as a :class:`GroupState`

        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def delete_group():
        """
        Deletes the scaling group if the state is empty.  This method should
        handle its own locking, if required.

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if the scaling group id
            doesn't exist for this tenant id
        :raises GroupNotEmptyError: if the scaling group cannot be
            deleted (e.g. if the state is not empty)
        """

    def update_status(status):
        """
        Updates the status of the group

        :param status: status to update
        :type status: One of the constants from
                      :class:`otter.models.interface.ScalingGroupStatus`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if the scaling group id
            doesn't exist for this tenant id
        """

    def update_config(config):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``config``.  This can update the already-existing values,
        or just overwrite them - it is up to the implementation.

        Enforcing the new min/max constraints should be done elsewhere.

        :param config: Configuration data in JSON format, as specified by
            :data:`otter.json_schema.group_schemas.config`
        :type config: :class:`dict`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def update_launch_config(launch_config):
        """
        Update the scaling group launch configuration parameters based on the
        attributes in ``launch_config``.  This can update the already-existing
        values, or just overwrite them - it is up to the implementation.

        :param launch_config: launch config data in JSON format, as specified
            by :data:`otter.json_schema.group_schemas.launch_config`
        :type launch_config: :class:`dict`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
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

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def create_policies(data):
        """
        Create a set of new scaling policies.

        :param data: a list of one or more scaling policies in JSON format,
            each of which is defined by
            :data:`otter.json_schema.group_schemas.policy`
        :type data: :class:`list` of :class:`dict`

        :return: list of newly created scaling policies and their ids, as
            specified by :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: :class:`list` of :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises PoliciesOverLimitError: if newly created policies
            breaches maximum policies per group
        """

    def update_policy(policy_id, data):
        """
        Updates an existing policy with the data given.

        :param policy_id: the uuid of the entity to update
        :type policy_id: :class:`bytes`

        :param data: the details of the scaling policy in JSON format
        :type data: :class:`dict`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises NoSuchPolicyError: if the policy id does not exist
        """

    def list_policies(limit=100, marker=None):
        """
        Gets all the policies associated with particular scaling group.

        :param int limit: the maximum number of policies to return
            (for pagination purposes)
        :param bytes marker: the policy ID of the last seen policy (for
            pagination purposes - page offsets)

        :return: a list of the policies, as specified by
            :data:`otter.json_schema.model_schemas.policy_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`list`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        """

    def get_policy(policy_id, version=None):
        """
        Gets the specified policy on this particular scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: :class:`bytes`

        :param version: version of policy to check as Type-1 UUID
        :type version: ``UUID``

        :return: a policy, as specified by
            :data:`otter.json_schema.group_schemas.policy`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`dict`

        :raises NoSuchPolicyError: if the policy id does not exist
        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist - this error is optional - a
            :class:`NoSuchPolicyError` can be raised instead
        """

    def delete_policy(policy_id):
        """
        Delete the specified policy on this particular scaling group, and all
        of its associated webhooks as well.

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: :class:`bytes`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises NoSuchPolicyError: if the policy id does not exist
        """

    def list_webhooks(policy_id, limit=100, marker=None):
        """
        Gets all the capability URLs created for one particular scaling policy

        :param int limit: the maximum number of policies to return
            (for pagination purposes)
        :param bytes marker: the policy ID of the last seen policy (for
            pagination purposes - page offsets)

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: :class:`bytes`

        :return: a list of the webhooks, as specified by
            :data:`otter.json_schema.model_schemas.webhook_list`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchPolicyError: if the policy id does not exist
        """

    def create_webhooks(policy_id, data):
        """
        Creates a new webhook for a scaling policy.

        The return value will contain both the webhook identifier (the
        identifier for the webhook resource itself, which allows an
        authenticated user to access and modify the webhook) as well as the
        capability hash (the unguessable identifier for a webhook which allows
        the referenced policy to be executed without further authentication).
        The REST layer turns these identifiers into URLs for the user.

        :param policy_id: The UUID of the policy for which to create a
            new webhook.
        :type policy_id: :class:`bytes`

        :param data: A list of details for each webhook, as specified by
            :data:`otter.json_schema.group_schemas.webhook`
        :type data: :class:`list` of :class:`dict`

        :return: A list of the created webhooks with their unique ids.
        :rtype: :class:`twisted.internet.defer.Deferred` :class:`list` as
            specified by :data:`otter.json_schema.model_schemas.webhook_list`

        :raises NoSuchPolicyError: if the policy id does not exist
        :raises WebhooksOverLimitError: if creating all the specified
            webhooks would put the user over their limit of webhooks per policy
        """

    def get_webhook(policy_id, webhook_id):
        """
        Gets the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: :class:`bytes`

        :param webhook_id: the uuid of the webhook
        :type webhook_id: :class:`bytes`

        :return: a webhook, as specified by
            :data:`otter.json_schema.model_schemas.webhook`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            :class:`dict`

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises NoSuchPolicyError: if the policy id does not exist
        :raises NoSuchWebhookError: if the webhook id does not exist
        """

    def update_webhook(policy_id, webhook_id, data):
        """
        Update the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: :class:`bytes`

        :param webhook_id: the uuid of the webhook
        :type webhook_id: :class:`bytes`

        :param data: the details of the scaling policy in JSON format
        :type data: :class:`dict`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises NoSuchPolicyError: if the policy id does not exist
        :raises NoSuchWebhookError: if the webhook id does not exist
        """

    def delete_webhook(policy_id, webhook_id):
        """
        Delete the specified webhook for the specified policy on this particular
        scaling group.

        :param policy_id: the uuid of the policy
        :type policy_id: :class:`bytes`

        :param webhook_id: the uuid of the webhook
        :type webhook_id: :class:`bytes`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises NoSuchScalingGroupError: if this scaling group (one
            with this uuid) does not exist
        :raises NoSuchPolicyError: if the policy id does not exist
        :raises NoSuchWebhookError: if the webhook id does not exist
        """


class IScalingGroupServersCache(Interface):
    """
    Cache of servers in scaling groups
    """
    tenant_id = Attribute("Rackspace Tenant ID of the owner of this group.")
    group_id = Attribute("UUID of the scaling group - immutable.")

    def get_servers():
        """
        Return latest cache of servers in a group along with last time the
        cache was updated.

        :return: Effect of (servers, last update time) tuple where servers
            is list of dict and last update time is datetime object. Will
            return last_update time as None if cache is empty
        :rtype: Effect
        """

    def insert_servers(last_update, servers, clear_others):
        """
        Update the servers cache of the group with last update time

        :param datetime last_update: Update time of the cache
        :param list servers: List of server dicts
        :param bool clear_others: Should any other cache from a different
            update_time be deleted?
        :return: Effect of None
        """

    def delete_servers():
        """
        Remove all servers of the group
        """


class IScalingScheduleCollection(Interface):
    """
    A list of scaling events in the future
    """
    def fetch_and_delete(bucket, now, size=100):
        """
        Fetch and delete a batch of scheduled events in a bucket.

        :param int bucket: Index of bucket from which to fetch events.
        :param datetime now: The current time.
        :param int size: The maximum number of events to fetch.
        :return: Deferred that fires with a sequence of events.
        :rtype: deferred :class:`list` of :class:`dict`
        """

    def add_cron_events(cron_events):
        """
        Add cron events equally distributed among the buckets.

        :param cron_events: List of events to be added.
        :type cron_events: :class:`list` of :class:`dict`
        :return: :data:`None`
        """

    def get_oldest_event(bucket):
        """
        Get the oldest event from a bucket.

        :param int bucket: Index of bucket from which to get the oldest event.
        :return: Deferred that fires with dict of oldest event
        :rtype: :class:`dict`
        """


def next_cron_occurrence(cron):
    """
    Return next occurence of given cron entry
    """
    return croniter(
        cron, start_time=datetime.utcnow()).get_next(ret_type=datetime)


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
        :type tenant_id: :class:`bytes`

        :param config: scaling group configuration options in JSON format, as
            specified by :data:`otter.json_schema.group_schemas.config`
        :type data: :class:`dict`

        :param launch: scaling group launch configuration options in JSON
            format, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :type data: :class:`dict`

        :param policies: list of scaling group policies, each one given as a
            JSON blob as specified by
            :data:`otter.json_schema.group_schemas.scaling_policy`
        :type data: :class:`list` of :class:`dict`

        :return: a dictionary corresponding to the JSON schema at
            :data:`otter.json_schema.model_schemas.manifest`, except that
            it also has the key `id`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with :class:`dict`
        """

    def list_scaling_group_states(log, tenant_id, limit=100, marker=None):
        """
        List the scaling groups states for this tenant ID

        :param tenant_id: the tenant ID of the scaling group info to list
        :type tenant_id: :class:`bytes`

        :param int limit: the maximum number of scaling group states to return
            (for pagination purposes)
        :param bytes marker: the group ID of the last seen group (for
            pagination purposes - page offsets)

        :return: a list of scaling group states
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            :class:`list` of :class:`GroupState`
        """

    def get_scaling_group(log, tenant_id, scaling_group_id):
        """
        Get a scaling group model

        Will return a scaling group even if the ID doesn't exist,
        but the scaling group will throw exceptions when you try to do things
        with it.

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: :class:`bytes`

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
        :type capability_hash: :class:`bytes`

        :return: a :class:`twisted.internet.defer.Deferred` that fires with
            a 3-tuple of (tenant_id, group_id, policy_id).

        :raises UnrecognizedCapabilityError: if the capability hash
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
        :type tenant_id: :class:`bytes`

        :return: a :class:`twisted.internet.defer.Deferred` containing current
            count of tenants policies, webhooks and groups as :class:`dict`
        """

    def health_check():
        """
        Check if the collection is healthy, and additionally provides some
        extra free-form health data.

        :return: The health information in the form of a boolean and some
            additional free-form health data (possibly empty).
        :rtype: deferred :class:`tuple` of (:class:`bool`, :class:`dict`)
        """


class IAdmin(Interface):
    """
    Interface to administrative information and actions.
    """

    def get_metrics(log):
        """
        Returns total current count of policies, webhooks and groups in the
        following format::

            {
                "groups": 100,
                "policies": 100,
                "webhooks": 100
            }

        :return: a :class:`twisted.internet.defer.Deferred` containing current
            count of tenants policies, webhooks and groups as :class:`dict`
        """
