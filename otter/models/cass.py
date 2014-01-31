"""
Cassandra implementation of the store for the front-end scaling groups engine
"""
import time
import itertools
import uuid
import functools

from zope.interface import implementer

from twisted.internet import defer, reactor
from jsonschema import ValidationError
from otter.models.interface import (
    GroupState, GroupNotEmptyError, IScalingGroup,
    IScalingGroupCollection, NoSuchScalingGroupError, NoSuchPolicyError,
    NoSuchWebhookError, UnrecognizedCapabilityError,
    IScalingScheduleCollection, IAdmin, ScalingGroupOverLimitError,
    WebhooksOverLimitError, PoliciesOverLimitError)
from otter.util.cqlbatch import Batch
from otter.util.hashkey import generate_capability, generate_key_str
from otter.util import timestamp
from otter.util.config import config_value
from otter.util.deferredutils import with_lock, timeout_deferred
from otter.scheduler import next_cron_occurrence

from silverberg.client import ConsistencyLevel

import json
from datetime import datetime

from kazoo.protocol.states import KazooState


LOCK_PATH = '/locks'


def serialize_json_data(data, ver):
    """
    Serialize json data to cassandra by adding a version and dumping it to a
    string
    """
    dataOut = data.copy()
    dataOut["_ver"] = ver
    return json.dumps(dataOut)

# ACHTUNG LOOKENPEEPERS!
#
# Batch operations don't let you have semicolons between statements.  Regular
# operations require you to end them with a semicolon.
#
# If you are doing a INSERT or UPDATE query, it's going to be part of a batch.
# Otherwise it won't.
#
# Thus, selects have a semicolon, everything else doesn't.
_cql_view = ('SELECT {column}, created_at FROM {cf} WHERE "tenantId" = :tenantId AND '
             '"groupId" = :groupId;')
_cql_view_policy = ('SELECT data, version FROM {cf} '
                    'WHERE "tenantId" = :tenantId AND "groupId" = :groupId AND '
                    '"policyId" = :policyId;')
_cql_view_webhook = ('SELECT data, capability FROM {cf} WHERE "tenantId" = :tenantId AND '
                     '"groupId" = :groupId AND "policyId" = :policyId AND '
                     '"webhookId" = :webhookId;')
_cql_create_group = ('INSERT INTO {cf}("tenantId", "groupId", group_config, launch_config, active, '
                     'pending, "policyTouched", paused, desired, created_at) '
                     'VALUES (:tenantId, :groupId, :group_config, :launch_config, :active, '
                     ':pending, :policyTouched, :paused, :desired, :created_at)')
_cql_view_manifest = ('SELECT "tenantId", "groupId", group_config, launch_config, active, '
                      'pending, "groupTouched", "policyTouched", paused, created_at '
                      'FROM {cf} WHERE "tenantId" = :tenantId AND "groupId" = :groupId')
_cql_insert_policy = (
    'INSERT INTO {cf}("tenantId", "groupId", "policyId", data, version) '
    'VALUES (:tenantId, :groupId, :{name}policyId, :{name}data, :{name}version)')
_cql_insert_group_state = ('INSERT INTO {cf}("tenantId", "groupId", active, pending, "groupTouched", '
                           '"policyTouched", paused, desired) VALUES(:tenantId, :groupId, :active, '
                           ':pending, :groupTouched, :policyTouched, :paused, :desired)')
_cql_view_group_state = ('SELECT "tenantId", "groupId", group_config, active, pending, "groupTouched", '
                         '"policyTouched", paused, desired, created_at FROM {cf} WHERE '
                         '"tenantId" = :tenantId AND "groupId" = :groupId;')

# --- Event related queries
_cql_insert_group_event = (
    'INSERT INTO {cf}(bucket, "tenantId", "groupId", "policyId", trigger, version) '
    'VALUES (:{name}bucket, :tenantId, :groupId, :{name}policyId, :{name}trigger, :{name}version)')
_cql_insert_group_event_with_cron = (
    'INSERT INTO {cf}(bucket, "tenantId", "groupId", "policyId", trigger, cron, version) '
    'VALUES (:{name}bucket, :tenantId, :groupId, :{name}policyId, :{name}trigger, '
    ':{name}cron, :{name}version)')
_cql_insert_cron_event = (
    'INSERT INTO {cf}(bucket, "tenantId", "groupId", "policyId", trigger, cron, version) '
    'VALUES (:{name}bucket, :{name}tenantId, :{name}groupId, :{name}policyId, '
    ':{name}trigger, :{name}cron, :{name}version);')
_cql_fetch_batch_of_events = (
    'SELECT "tenantId", "groupId", "policyId", "trigger", cron, version FROM {cf} '
    'WHERE bucket = :bucket AND trigger <= :now LIMIT :size;')
_cql_delete_bucket_event = ('DELETE FROM {cf} WHERE bucket = :bucket '
                            'AND trigger = :{name}trigger AND "policyId" = :{name}policyId;')
_cql_oldest_event = 'SELECT * from {cf} WHERE bucket=:bucket LIMIT 1;'

_cql_insert_webhook = (
    'INSERT INTO {cf}("tenantId", "groupId", "policyId", "webhookId", data, capability, '
    '"webhookKey") VALUES (:tenantId, :groupId, :policyId, :{name}Id, :{name}, '
    ':{name}Capability, :{name}Key)')
_cql_update = ('INSERT INTO {cf}("tenantId", "groupId", {column}) '
               'VALUES (:tenantId, :groupId, {name})')
_cql_update_webhook = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", "webhookId", data) '
                       'VALUES (:tenantId, :groupId, :policyId, :webhookId, :data);')
_cql_delete_all_in_group = ('DELETE FROM {cf} WHERE "tenantId" = :tenantId AND '
                            '"groupId" = :groupId{name}')
_cql_delete_all_in_policy = ('DELETE FROM {cf} WHERE "tenantId" = :tenantId '
                             'AND "groupId" = :groupId AND "policyId" = :policyId')
_cql_delete_one_webhook = ('DELETE FROM {cf} WHERE "tenantId" = :tenantId AND '
                           '"groupId" = :groupId AND "policyId" = :policyId AND '
                           '"webhookId" = :webhookId')
_cql_list_states = ('SELECT "tenantId", "groupId", group_config, active, pending, "groupTouched", '
                    '"policyTouched", paused, created_at FROM {cf} WHERE '
                    '"tenantId" = :tenantId;')
_cql_list_policy = ('SELECT "policyId", data FROM {cf} WHERE '
                    '"tenantId" = :tenantId AND "groupId" = :groupId;')
_cql_list_webhook = ('SELECT "webhookId", data, capability FROM {cf} '
                     'WHERE "tenantId" = :tenantId AND "groupId" = :groupId AND '
                     '"policyId" = :policyId;')

_cql_find_webhook_token = ('SELECT "tenantId", "groupId", "policyId" FROM {cf} WHERE '
                           '"webhookKey" = :webhookKey;')

_cql_count_for_tenant = ('SELECT COUNT(*) FROM {cf} WHERE "tenantId" = :tenantId;')
_cql_count_for_policy = ('SELECT COUNT(*) FROM {cf} WHERE '
                         '"tenantId" = :tenantId AND "groupId" = :groupId AND '
                         '"policyId" = :policyId;')
_cql_count_for_group = ('SELECT COUNT(*) FROM {cf} WHERE "tenantId" = :tenantId '
                        'AND "groupId" = :groupId;')
_cql_count_all = ('SELECT COUNT(*) FROM {cf};')

# seems to be pretty quick no matter the consistency - unfortunately this only checks
# connectability to cassandra, and not whether the otter keyspace is correct, etc.
_cql_health_check = ('SELECT now() FROM system.local;')


def _paginated_list(tenant_id, group_id=None, policy_id=None, limit=100,
                    marker=None):
    """
    :param tenant_id: the tenant ID - if this is all that is provided, this
        function returns cql to list all groups

    :param group_id: the group ID - if this and tenant ID are all that is
        provided, this function returns cql to list all policies.

    :param policy_id: the policyID - if this and gorupID and tenant ID are
        provided, this function returns cql to list all webhooks.  Note that
        if this is provided and groupID is not provided, the policy ID will be
        ignored and cql to list all groups will be returned.

    :param marker: the ID of the last column of the provided keys. (e.g.
        group_id, when listing groups, policy_id, when listing policies,
        and webhook_id, when listing webhooks)

    :param limit: is the number of items to fetch

    :returns: a tuple of cql and a dict of the parameters to provide when
        executing that CQL.

    The CQL will look like:

        SELECT "policyId", data FROM {cf} WHERE "tenantId" = :tenantId AND
        "groupId" = :groupId AND "policyId" > :marker LIMIT 100;

    Note that the column family name still has to be inserted.

    Also, no ``ORDER BY`` is in the CQL, since for these are all primary keys
    sorted by cluster order (e.g. if you get all scaling groups for a tenant,
    the groups will be returned in ascending order of group ID, and if you get
    all policies for a scaling group, they will be returned in ascending order
    of policy ID)

    See http://cassandra.apache.org/doc/cql3/CQL.html#createTableOptions
    """
    params = {'tenantId': tenant_id, 'limit': limit}
    marker_cql = ''

    if marker is not None:
        marker_cql = " AND {0} > :marker"
        params['marker'] = marker

    if group_id is not None:
        params['groupId'] = group_id

        if policy_id is not None:
            params['policyId'] = policy_id
            cql_parts = [_cql_list_webhook.rstrip(';'),
                         marker_cql.format('"webhookId"')]
        else:
            cql_parts = [_cql_list_policy.rstrip(';'),
                         marker_cql.format('"policyId"')]
    else:
        cql_parts = [_cql_list_states.rstrip(';'),
                     marker_cql.format('"groupId"')]

    cql_parts.append(" LIMIT :limit;")
    return (''.join(cql_parts), params)


# Store consistency levels
_consistency_levels = {'event': {'fetch': ConsistencyLevel.QUORUM,
                                 'insert': ConsistencyLevel.ONE,
                                 'delete': ConsistencyLevel.QUORUM},
                       'group': {'create': ConsistencyLevel.QUORUM},
                       'state': {'update': ConsistencyLevel.QUORUM}}


def get_consistency_level(operation, resource):
    """
    Get the consistency level for a particular operation.

    :param operation: one of (create, list, view, update, or delete)
    :type operation: ``str``

    :param resource: one of (group, partial, policy, webhook) -
        "partial" covers group views such as the config, the launch
        config, or the state
    :type resource: ``str``

    :return: the consistency level
    :rtype: one of the consistency levels in :class:`ConsistencyLevel`
    """
    # TODO: configurable consistency level, possibly different for read
    # and write operations
    resource_operations = _consistency_levels.get(resource)
    if resource_operations:
        return resource_operations.get(operation, ConsistencyLevel.ONE)
    else:
        return ConsistencyLevel.ONE


def _build_policies(policies, policies_table, event_table, queries, data, buckets):
    """
    Because inserting many values into a table with compound keys with one
    insert statement is hard. This builds a bunch of insert statements and a
    dictionary matching different parameter names to different policies.

    :param policies: a list of policy data without ID
    :type policies: ``list`` of ``dict``

    :param policies_table: the name of the policies table
    :type policies_table: ``str``

    :param queries: a list of existing CQL queries to add to
    :type queries: ``list`` of ``str``

    :param data: the dictionary of named parameters and values passed in
        addition to the query to execute the query
    :type data: ``dict``

    :returns: a ``list`` of the created policies along with their generated IDs
    """
    outpolicies = []

    if policies is not None:
        for i, policy in enumerate(policies):
            polname = "policy{}".format(i)
            polId = generate_key_str('policy')
            queries.append(_cql_insert_policy.format(cf=policies_table,
                                                     name=polname))

            data[polname + 'data'] = serialize_json_data(policy, 1)
            data[polname + 'policyId'] = polId
            data[polname + 'version'] = uuid.uuid1()

            if policy.get("type") == 'schedule':
                _build_schedule_policy(policy, event_table, queries,
                                       data, polname, buckets)

            outpolicies.append(policy.copy())
            outpolicies[-1]['id'] = polId

    return outpolicies


def _build_schedule_policy(policy, event_table, queries, data, polname, buckets):
    """
    Build schedule-type policy
    """
    data[polname + 'bucket'] = buckets.next()
    if 'at' in policy["args"]:
        queries.append(_cql_insert_group_event.format(cf=event_table, name=polname))
        at_time = timestamp.from_timestamp(policy["args"]["at"])
        data[polname + "trigger"] = at_time
    elif 'cron' in policy["args"]:
        queries.append(
            _cql_insert_group_event_with_cron.format(cf=event_table, name=polname))
        cron = policy["args"]["cron"]
        data[polname + "trigger"] = next_cron_occurrence(cron)
        data[polname + 'cron'] = cron


def _build_webhooks(bare_webhooks, webhooks_table, queries, cql_parameters):
    """
    Because inserting many values into a table with compound keys with one
    insert statement is hard. This builds a bunch of insert statements and a
    dictionary matching different parameter names to different policies.

    :param bare_webhooks: a list of webhook data without ID or webhook keys,
        or any generated capability hash info
    :type bare_webhooks: ``list`` of ``dict``

    :param webhooks_table: the name of the webhooks table
    :type webhooks_table: ``str``

    :param queries: a list of existing CQL queries to add to
    :type queries: ``list`` of ``str``

    :param cql_parameters: the dictionary of named parameters and values passed
        in addition to the query to execute the query - additional parameters
        will be added to this dictionary
    :type cql_paramters: ``dict``

    :returns: ``list`` of the created webhooks along with their IDs
    """
    output = []
    for i, webhook in enumerate(bare_webhooks):
        name = "webhook{0}".format(i)
        webhook_id = generate_key_str('webhook')
        queries.append(_cql_insert_webhook.format(cf=webhooks_table,
                                                  name=name))

        # generate the real data that will be stored, which includes the webhook
        # token, the capability stuff, and metadata by default
        bare_webhooks[i].setdefault('metadata', {})
        version, cap_hash = generate_capability()

        cql_parameters[name] = serialize_json_data(webhook, 1)
        cql_parameters['{0}Id'.format(name)] = webhook_id
        cql_parameters['{0}Key'.format(name)] = cap_hash
        cql_parameters['{0}Capability'.format(name)] = serialize_json_data(
            {version: cap_hash}, 1)

        output.append(dict(id=webhook_id,
                           capability={'hash': cap_hash, 'version': version},
                           **webhook))
    return output


def _assemble_webhook_from_row(row, include_id=False):
    """
    Builds a webhook as per :data:`otter.json_schema.model_schemas.webhook`
    from the user-mutable user data (name and metadata) and the
    non-user-mutable capability data.

    :param dict row: a dictionary of cassandra data containing the key
        ``data`` (the user-mutable data) and the key ``capability`` (the
        capability info, stored in cassandra as: `{<version>: <capability hash>}`)

    :return: the webhook, as per :data:`otter.json_schema.model_schemas.webhook`
    :rtype: ``dict``
    """
    webhook_base = _jsonloads_data(row['data'])
    capability_data = _jsonloads_data(row['capability'])

    version, cap_hash = capability_data.iteritems().next()
    webhook_base['capability'] = {'version': version, 'hash': cap_hash}

    if include_id:
        webhook_base['id'] = row['webhookId']

    return webhook_base


def _check_empty_and_grab_data(results, exception_if_empty):
    if len(results) == 0:
        raise exception_if_empty
    return _jsonloads_data(results[0]['data'])


def _jsonloads_data(raw_data):
    data = json.loads(raw_data)
    if "_ver" in data:
        del data["_ver"]
    return data


def _unmarshal_state(state_dict):
    desired_capacity = state_dict['desired']
    if desired_capacity is None:
        desired_capacity = 0

    return GroupState(
        state_dict["tenantId"], state_dict["groupId"],
        _jsonloads_data(state_dict["group_config"])["name"],
        _jsonloads_data(state_dict["active"]),
        _jsonloads_data(state_dict["pending"]),
        state_dict["groupTouched"],
        _jsonloads_data(state_dict["policyTouched"]),
        bool(ord(state_dict["paused"])),
        desired=desired_capacity
    )


def verified_view(connection, view_query, del_query, data, consistency, exception_if_empty, log):
    """
    Ensures the view query does not get resurrected row, i.e. one that does not have "created_at" in it.
    Any resurrected entry is deleted and `exception_if_empty` is raised.
    TODO: Should there be seperate argument for view_consistency and del_consistency
    """
    def _check_resurrection(result):
        if len(result) == 0:
            raise exception_if_empty
        if result[0].get('created_at'):
            return result[0]
        else:
            # resurrected row, trigger its deletion and raise empty exception
            log.msg('Resurrected row', row=result[0], row_params=data)
            connection.execute(del_query, data, consistency)
            raise exception_if_empty

    d = connection.execute(view_query, data, consistency)
    return d.addCallback(_check_resurrection)


@implementer(IScalingGroup)
class CassScalingGroup(object):
    """
    .. autointerface:: otter.models.interface.IScalingGroup

    :ivar tenant_id: the tenant ID of the scaling group - once set, should not
        be updated
    :type tenant_id: ``str``

    :ivar uuid: UUID of the scaling group - once set, cannot be updated
    :type uuid: ``str``

    :ivar connection: silverberg client used to connect to cassandra
    :type connection: :class:`silverberg.client.CQLClient`

    IMPORTANT REMINDER: In CQL, update will create a new row if one doesn't
    exist.  Therefore, before doing an update, a read must be performed first
    else an entry is created where none should have been.

    Cassandra doesn't have atomic read-update.  You can't be guaranteed that the
    previous state (from the read) hasn't changed between when you got it back
    from Cassandra and when you are sending your new update/insert request.

    Also, because deletes are done as tombstones rather than actually deleting,
    deletes are also updates and hence a read must be performed before deletes.
    """
    def __init__(self, log, tenant_id, uuid, connection, buckets, kz_client):
        """
        Creates a CassScalingGroup object.
        """
        self.log = log.bind(system=self.__class__.__name__,
                            tenant_id=tenant_id,
                            scaling_group_id=uuid)
        self.tenant_id = tenant_id
        self.uuid = uuid
        self.connection = connection
        self.buckets = buckets
        self.kz_client = kz_client
        self.group_table = "scaling_group"
        self.launch_table = "launch_config"
        self.policies_table = "scaling_policies"
        self.state_table = "group_state"
        self.webhooks_table = "policy_webhooks"
        self.event_table = "scaling_schedule_v2"

    def view_manifest(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_manifest`
        """
        def _get_policies(group):
            """
            Now that we know the group exists, get its policies
            """
            limit = config_value('limits.pagination') or 100
            d = self._naive_list_policies(limit=limit)
            d.addCallback(lambda policies: {
                'groupConfiguration': _jsonloads_data(group['group_config']),
                'launchConfiguration': _jsonloads_data(group['launch_config']),
                'scalingPolicies': policies,
                'id': self.uuid,
                'state': _unmarshal_state(group)
            })
            return d

        view_query = _cql_view_manifest.format(cf=self.group_table)
        del_query = _cql_delete_all_in_group.format(cf=self.group_table, name='')
        d = verified_view(self.connection, view_query, del_query,
                          {"tenantId": self.tenant_id,
                           "groupId": self.uuid},
                          get_consistency_level('view', 'group'),
                          NoSuchScalingGroupError(self.tenant_id, self.uuid), self.log)
        d.addCallback(_get_policies)
        return d

    def view_config(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_config`
        """
        view_query = _cql_view.format(cf=self.group_table, column='group_config')
        del_query = _cql_delete_all_in_group.format(cf=self.group_table, name='')
        d = verified_view(self.connection, view_query, del_query,
                          {"tenantId": self.tenant_id,
                           "groupId": self.uuid},
                          get_consistency_level('view', 'partial'),
                          NoSuchScalingGroupError(self.tenant_id, self.uuid), self.log)

        return d.addCallback(lambda group: _jsonloads_data(group['group_config']))

    def view_launch_config(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_launch_config`
        """
        view_query = _cql_view.format(cf=self.group_table, column='launch_config')
        del_query = _cql_delete_all_in_group.format(cf=self.group_table, name='')
        d = verified_view(self.connection, view_query, del_query,
                          {"tenantId": self.tenant_id,
                           "groupId": self.uuid},
                          get_consistency_level('view', 'partial'),
                          NoSuchScalingGroupError(self.tenant_id, self.uuid), self.log)

        return d.addCallback(lambda group: _jsonloads_data(group['launch_config']))

    def view_state(self, consistency=None):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_state`
        """
        if consistency is None:
            consistency = get_consistency_level('view', 'partial')

        view_query = _cql_view_group_state.format(cf=self.group_table)
        del_query = _cql_delete_all_in_group.format(cf=self.group_table, name='')
        d = verified_view(self.connection, view_query, del_query,
                          {"tenantId": self.tenant_id,
                           "groupId": self.uuid},
                          consistency,
                          NoSuchScalingGroupError(self.tenant_id, self.uuid), self.log)

        return d.addCallback(_unmarshal_state)

    def modify_state(self, modifier_callable, *args, **kwargs):
        """
        see :meth:`otter.models.interface.IScalingGroup.modify_state`
        """
        log = self.log.bind(system='CassScalingGroup.modify_state')
        consistency = get_consistency_level('update', 'state')

        def _write_state(new_state):
            assert (new_state.tenant_id == self.tenant_id and
                    new_state.group_id == self.uuid)
            params = {
                'tenantId': new_state.tenant_id,
                'groupId': new_state.group_id,
                'active': serialize_json_data(new_state.active, 1),
                'pending': serialize_json_data(new_state.pending, 1),
                'paused': new_state.paused,
                'desired': new_state.desired,
                'groupTouched': new_state.group_touched,
                'policyTouched': serialize_json_data(new_state.policy_touched, 1)
            }
            return self.connection.execute(_cql_insert_group_state.format(cf=self.group_table),
                                           params, consistency)

        def _modify_state():
            d = self.view_state(consistency)
            d.addCallback(lambda state: modifier_callable(self, state, *args, **kwargs))
            return d.addCallback(_write_state)

        lock = self.kz_client.Lock(LOCK_PATH + '/' + self.uuid)
        lock.acquire = functools.partial(lock.acquire, timeout=120)
        # TODO: Better way to get reactor instead of importing?
        return with_lock(reactor, lock, log.bind(category='locking'), _modify_state)

    def update_config(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_config`
        """
        self.log.bind(updated_config=data).msg("Updating config")

        def _do_update_config(lastRev):
            queries = [_cql_update.format(cf=self.group_table, column='group_config',
                                          name=":scaling")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "scaling": serialize_json_data(data, 1)},
                      consistency=get_consistency_level('update', 'partial'))
            return b.execute(self.connection)

        d = self.view_config()
        d.addCallback(_do_update_config)
        return d

    def update_launch_config(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_launch_config`
        """
        self.log.bind(updated_launch_config=data).msg("Updating launch config")

        def _do_update_launch(lastRev):
            queries = [_cql_update.format(cf=self.group_table, column='launch_config',
                                          name=":launch")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "launch": serialize_json_data(data, 1)},
                      consistency=get_consistency_level('update', 'partial'))
            d = b.execute(self.connection)
            return d

        d = self.view_config()
        d.addCallback(_do_update_launch)
        return d

    def _naive_list_policies(self, limit=None, marker=None):
        """
        Like :meth:`otter.models.cass.CassScalingGroup.list_policies`, but gets
        all the policies associated with particular scaling group
        irregardless of whether the scaling group still exists.
        """
        def insert_id(rows):
            return [dict(id=row['policyId'], **_jsonloads_data(row['data']))
                    for row in rows]

        # TODO: this is just in place so that pagination in the manifest can
        # be handled elsewhere
        if limit is not None:
            cql, params = _paginated_list(self.tenant_id, self.uuid,
                                          limit=limit, marker=marker)
        else:
            cql = _cql_list_policy
            params = {"tenantId": self.tenant_id, "groupId": self.uuid}

        d = self.connection.execute(cql.format(cf=self.policies_table), params,
                                    get_consistency_level('list', 'policy'))
        d.addCallback(insert_id)
        return d

    def list_policies(self, limit=100, marker=None):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_policies`
        """
        # If there are no policies - make sure it's not because the group
        # doesn't exist
        def _check_if_empty(policies_dict):
            if len(policies_dict) == 0:
                return self.view_config().addCallback(lambda _: policies_dict)
            return policies_dict

        d = self._naive_list_policies(limit=limit, marker=marker)
        return d.addCallback(_check_if_empty)

    def get_policy(self, policy_id, version=None):
        """
        see :meth:`otter.models.interface.IScalingGroup.get_policy`
        """
        query = _cql_view_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid,
                                     "policyId": policy_id},
                                    get_consistency_level('view', 'policy'))

        def _extract_policy(rows):
            if len(rows) == 0 or version and rows[0]['version'] != version:
                raise NoSuchPolicyError(self.tenant_id, self.uuid, policy_id)
            return _jsonloads_data(rows[0]['data'])

        return d.addCallback(_extract_policy)

    def create_policies(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.create_policies`
        """
        self.log.bind(policies=data).msg("Creating policies")

        def _do_limits_check(lastRev):
            d = self.connection.execute(
                _cql_count_for_group.format(cf=self.policies_table),
                {"tenantId": self.tenant_id,
                 "groupId": self.uuid},
                get_consistency_level("count", "policies"))
            return d.addCallback(_check_limit).addCallback(lambda _: lastRev)

        def _check_limit(curr_policies):
            max_policies = config_value('limits.absolute.maxPoliciesPerGroup')
            curr_policies = curr_policies[0]['count']
            if curr_policies + len(data) > max_policies:
                raise PoliciesOverLimitError(
                    curr_policies=curr_policies,
                    max_policies=max_policies,
                    new_policies=len(data),
                    tenant_id=self.tenant_id,
                    group_id=self.uuid)

        def _do_create_pol(lastRev):
            queries = []
            cqldata = {"tenantId": self.tenant_id,
                       "groupId": self.uuid}

            outpolicies = _build_policies(data, self.policies_table,
                                          self.event_table, queries, cqldata,
                                          self.buckets)

            b = Batch(queries, cqldata,
                      consistency=get_consistency_level('create', 'policy'))
            d = b.execute(self.connection)
            return d.addCallback(lambda _: outpolicies)

        d = self.view_config()
        d.addCallback(_do_limits_check)
        d.addCallback(_do_create_pol)
        return d

    def update_policy(self, policy_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_policy`
        """
        self.log.bind(updated_policy=data, policy_id=policy_id).msg("Updating policy")

        queries = []
        cqldata = {'tenantId': self.tenant_id, 'groupId': self.uuid, 'policyId': policy_id,
                   'version': uuid.uuid1()}

        def _do_update_schedule(lastRev):
            if "type" in lastRev:
                if lastRev["type"] != data["type"]:
                    raise ValidationError("Cannot change type of a scaling policy")
                if lastRev["type"] == 'schedule':
                    _build_schedule_policy(data, self.event_table, queries,
                                           cqldata, '', self.buckets)

        def _do_update_policy(_):
            queries.append(_cql_insert_policy.format(cf=self.policies_table, name=""))
            cqldata['data'] = serialize_json_data(data, 1)
            b = Batch(queries, cqldata,
                      consistency=get_consistency_level('update', 'policy'))
            return b.execute(self.connection)

        d = self.get_policy(policy_id)
        d.addCallback(_do_update_schedule)
        d.addCallback(_do_update_policy)
        return d

    def delete_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_policy`
        """
        self.log.bind(policy_id=policy_id).msg("Deleting policy")

        def _do_delete(_):
            queries = [
                _cql_delete_all_in_policy.format(cf=self.policies_table),
                _cql_delete_all_in_policy.format(cf=self.webhooks_table)]
            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "policyId": policy_id},
                      consistency=get_consistency_level('delete', 'policy'))
            return b.execute(self.connection)

        d = self.get_policy(policy_id)
        d.addCallback(_do_delete)
        return d

    def _naive_list_webhooks(self, policy_id, limit, marker):
        """
        Like :meth:`otter.models.cass.CassScalingGroup.list_webhooks`, but gets
        all the webhooks associated with particular scaling policy
        irregardless of whether the scaling policy still exists.
        """
        def _assemble_webhook_results(results):
            return [_assemble_webhook_from_row(row, include_id=True)
                    for row in results]

        cql, params = _paginated_list(self.tenant_id, self.uuid, policy_id,
                                      limit=limit, marker=marker)

        d = self.connection.execute(cql.format(cf=self.webhooks_table), params,
                                    get_consistency_level('list', 'webhook'))
        d.addCallback(_assemble_webhook_results)
        return d

    def list_webhooks(self, policy_id, limit=100, marker=None):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_webhooks`
        """
        def _check_if_empty(webhooks_dict):
            if len(webhooks_dict) == 0:
                policy_there = self.get_policy(policy_id)
                return policy_there.addCallback(lambda _: webhooks_dict)
            return webhooks_dict

        d = self._naive_list_webhooks(policy_id, limit=limit, marker=marker)
        d.addCallback(_check_if_empty)
        return d

    def create_webhooks(self, policy_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.create_webhooks`
        """
        self.log.bind(policy_id=policy_id, webhook=data).msg("Creating webhooks")

        main_params = {"tenantId": self.tenant_id,
                       "groupId": self.uuid,
                       "policyId": policy_id}

        d = self.get_policy(policy_id)  # check that policy exists first

        def _check_limit(curr_webhooks):
            max_webhooks = config_value('limits.absolute.maxWebhooksPerPolicy')
            curr_webhooks = curr_webhooks[0]['count']
            if curr_webhooks + len(data) > max_webhooks:
                raise WebhooksOverLimitError(
                    curr_webhooks=curr_webhooks,
                    max_webhooks=max_webhooks,
                    new_webhooks=len(data),
                    tenant_id=self.tenant_id,
                    group_id=self.uuid,
                    policy_id=policy_id)

        def _do_limits_check(lastRev):
            d = self.connection.execute(
                _cql_count_for_policy.format(cf=self.webhooks_table),
                main_params,
                get_consistency_level('count', 'webhook'))
            return d.addCallback(_check_limit).addCallback(lambda _: lastRev)

        d.addCallback(_do_limits_check)

        def _do_create(lastRev):
            queries = []
            cql_params = main_params.copy()
            output = _build_webhooks(data, self.webhooks_table, queries,
                                     cql_params)

            b = Batch(queries, cql_params,
                      consistency=get_consistency_level('create', 'webhook'))
            d = b.execute(self.connection)
            return d.addCallback(lambda _: output)

        d.addCallback(_do_create)
        return d

    def get_webhook(self, policy_id, webhook_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.get_webhook`
        """
        def _assemble_webhook(cass_data):
            if len(cass_data) == 0:
                raise NoSuchWebhookError(self.tenant_id, self.uuid, policy_id,
                                         webhook_id)
            return _assemble_webhook_from_row(cass_data[0])

        query = _cql_view_webhook.format(cf=self.webhooks_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid,
                                     "policyId": policy_id,
                                     "webhookId": webhook_id},
                                    get_consistency_level('view', 'webhook'))
        d.addCallback(_assemble_webhook)
        return d

    def update_webhook(self, policy_id, webhook_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_webhook`
        """
        self.log.bind(policy_id=policy_id, webhook_id=webhook_id,
                      webhook=data).msg("Updating webhook")

        def _update_data(lastRev):
            data.setdefault('metadata', {})
            query = _cql_update_webhook.format(cf=self.webhooks_table)
            return self.connection.execute(
                query,
                {"tenantId": self.tenant_id,
                 "groupId": self.uuid,
                 "policyId": policy_id,
                 "webhookId": webhook_id,
                 "data": serialize_json_data(data, 1)},
                get_consistency_level('update', 'webhook'))

        d = self.get_webhook(policy_id, webhook_id)
        return d.addCallback(_update_data)

    def delete_webhook(self, policy_id, webhook_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_webhook`
        """
        self.log.bind(policy_id=policy_id, webhook_id=webhook_id).msg("Deleting webhook")

        def _do_delete(lastRev):
            query = _cql_delete_one_webhook.format(cf=self.webhooks_table)

            d = self.connection.execute(query,
                                        {"tenantId": self.tenant_id,
                                         "groupId": self.uuid,
                                         "policyId": policy_id,
                                         "webhookId": webhook_id},
                                        get_consistency_level('delete', 'webhook'))
            return d

        return self.get_webhook(policy_id, webhook_id).addCallback(_do_delete)

    def delete_group(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_group`
        """
        log = self.log.bind(system='CassScalingGroup.delete_group')

        # Events can only be deleted by policy id, since that and trigger are
        # the only parts of the compound key
        def _delete_everything(policies):
            params = {
                'tenantId': self.tenant_id,
                'groupId': self.uuid
            }
            queries = [
                _cql_delete_all_in_group.format(cf=table, name='') for table in
                (self.group_table, self.policies_table, self.webhooks_table)]

            b = Batch(queries, params,
                      consistency=get_consistency_level('delete', 'group'))

            return b.execute(self.connection)

        def _maybe_delete(state):
            if len(state.active) + len(state.pending) > 0:
                raise GroupNotEmptyError(self.tenant_id, self.uuid)

            d = self._naive_list_policies()
            d.addCallback(_delete_everything)
            return d

        def _delete_group():
            d = self.view_state()
            d.addCallback(_maybe_delete)
            return d

        lock = self.kz_client.Lock(LOCK_PATH + '/' + self.uuid)
        lock.acquire = functools.partial(lock.acquire, timeout=120)
        return with_lock(reactor, lock, log.bind(category='locking'), _delete_group)


@implementer(IScalingGroupCollection, IScalingScheduleCollection)
class CassScalingGroupCollection:
    """
    .. autointerface:: otter.models.interface.IScalingGroupCollection

    The Cassandra schema structure::

        Configs:
        CF = scaling_group
        RK = tenantId
        CK = groupID

        Launch Configs (mirrors config):
        CF = launch_config
        RK = tenantId
        CK = groupID

        Scaling Policies (doesn't mirror config):
        CF = policies
        RK = tenantId
        CK = groupID:policyId

    IMPORTANT REMINDER: In CQL, update will create a new row if one doesn't
    exist.  Therefore, before doing an update, a read must be performed first
    else an entry is created where none should have been.

    Cassandra doesn't have atomic read-update.  You can't be guaranteed that the
    previous state (from the read) hasn't changed between when you got it back
    from Cassandra and when you are sending your new update/insert request.

    Also, because deletes are done as tombstones rather than actually deleting,
    deletes are also updates and hence a read must be performed before deletes.
    """
    def __init__(self, connection):
        """
        Init

        :param connection: Thrift connection to use

        :param cflist: Column family list
        """
        self.connection = connection
        self.group_table = "scaling_group"
        self.launch_table = "launch_config"
        self.policies_table = "scaling_policies"
        self.webhooks_table = "policy_webhooks"
        self.state_table = "group_state"
        self.event_table = "scaling_schedule_v2"
        self.buckets = None
        self.kz_client = None

    def set_scheduler_buckets(self, buckets):
        """
        Set round-robin list of buckets that will be used to store scheduled events
        """
        self.buckets = itertools.cycle(buckets)

    def create_scaling_group(self, log, tenant_id, config, launch, policies=None):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.create_scaling_group`
        """
        scaling_group_id = generate_key_str('scalinggroup')
        log = log.bind(tenant_id=tenant_id, scaling_group_id=scaling_group_id)

        # obey limits
        max_groups = config_value('limits.absolute.maxGroups')
        d = self.connection.execute(_cql_count_for_tenant.format(
            cf="scaling_group"), {'tenantId': tenant_id},
            get_consistency_level('list', 'group'))

        def check_groups(cur_groups, max_groups):
            if cur_groups[0]['count'] >= max_groups:
                log.msg('client has reached maxGroups limit')
                raise ScalingGroupOverLimitError(tenant_id, max_groups)

        d.addCallback(check_groups, max_groups)

        def _create_group(_):
            log.msg("Creating scaling group")
            queries = [_cql_create_group.format(cf=self.group_table)]

            data = {
                "tenantId": tenant_id,
                "groupId": scaling_group_id,
                "group_config": serialize_json_data(config, 1),
                "launch_config": serialize_json_data(launch, 1),
                "active": '{}',
                "pending": '{}',
                "created_at": datetime.utcnow(),
                "policyTouched": '{}',
                "paused": False,
                "desired": config.get('minEntities', 0)
            }

            scaling_group_state = GroupState(
                tenant_id,
                scaling_group_id,
                config['name'],
                {},
                {},
                data['created_at'],
                {},
                data['paused'],
                desired=data['desired']
            )
            outpolicies = _build_policies(policies, self.policies_table,
                                          self.event_table, queries, data, self.buckets)

            b = Batch(queries, data,
                      consistency=get_consistency_level('create', 'group'))

            bd = b.execute(self.connection)
            bd.addCallback(lambda _: {
                'groupConfiguration': config,
                'launchConfiguration': launch,
                'scalingPolicies': outpolicies,
                'id': scaling_group_id,
                'state': scaling_group_state
            })

            return bd

        return d.addCallback(_create_group)

    def list_scaling_group_states(self, log, tenant_id, limit=100, marker=None):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.list_scaling_group_states`
        """
        def _build_states(group_states):
            return [_unmarshal_state(state) for state in group_states]

        def _filter_resurrected(groups):
            valid_groups, resurrected_groups = [], []
            for group in groups:
                if group['created_at']:
                    valid_groups.append(group)
                else:
                    resurrected_groups.append(group)
            # We can trigger deletion of resurrected groups and return valid_groups right away
            # We need not wait till deletion completes.
            _delete_resurrected_groups(resurrected_groups)
            return valid_groups

        def _delete_resurrected_groups(groups):
            if not groups:
                return None
            log.msg('Resurrected rows', rows=groups)

            queries = [
                _cql_delete_all_in_group.format(cf=table, name=i)
                for table in (self.group_table, self.policies_table, self.webhooks_table)
                for i in range(len(groups))]

            params = {'groupId{0}'.format(i): group['groupId']
                      for i, group in enumerate(groups)}
            params['tenantId'] = tenant_id

            b = Batch(queries, params, get_consistency_level('delete', 'group'))
            return b.execute(self.connection)

        log = log.bind(tenant_id=tenant_id)
        cql, params = _paginated_list(tenant_id, limit=limit, marker=marker)
        d = self.connection.execute(cql.format(cf=self.group_table), params,
                                    get_consistency_level('list', 'group'))
        d.addCallback(_filter_resurrected)
        d.addCallback(_build_states)
        return d

    def get_scaling_group(self, log, tenant_id, scaling_group_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.get_scaling_group`
        """
        return CassScalingGroup(log, tenant_id, scaling_group_id,
                                self.connection, self.buckets, self.kz_client)

    def fetch_and_delete(self, bucket, now, size=100):
        """
        Fetch events to be occurring now or before in a bucket
        and delete them after fetching
        """
        def delete_events(events):
            if not events:
                return events
            data = {'bucket': bucket}
            queries = []
            for i, event in enumerate(events):
                event_name = 'event{}'.format(i)
                queries.append(
                    _cql_delete_bucket_event.format(cf=self.event_table,
                                                    name=event_name))
                data[event_name + 'policyId'] = event['policyId']
                data[event_name + 'trigger'] = event['trigger']
            b = Batch(queries, data, get_consistency_level('delete', 'event'))
            return b.execute(self.connection).addCallback(lambda _: events)

        d = self.connection.execute(_cql_fetch_batch_of_events.format(cf=self.event_table),
                                    {"size": size, "now": now, "bucket": bucket},
                                    get_consistency_level('fetch', 'event'))
        return d.addCallback(delete_events)

    def add_cron_events(self, cron_events):
        """
        Add cron events to event table
        """
        queries, data = list(), dict()
        for i, event in enumerate(cron_events):
            event_name = 'event{}'.format(i)
            queries.append(_cql_insert_cron_event.format(cf=self.event_table,
                                                         name=event_name))
            data[event_name + 'bucket'] = self.buckets.next()
            data.update({event_name + key: event[key] for key in event})
        b = Batch(queries, data, get_consistency_level('insert', 'event'))
        return b.execute(self.connection)

    def get_oldest_event(self, bucket):
        """
        see :meth:`otter.models.interface.IScalingScheduleCollection.get_oldest_event`
        """
        d = self.connection.execute(_cql_oldest_event.format(cf=self.event_table),
                                    {'bucket': bucket},
                                    get_consistency_level('check', 'event'))
        d.addCallback(lambda r: r[0] if len(r) > 0 else None)
        return d

    def webhook_info_by_hash(self, log, capability_hash):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.webhook_info_by_hash`
        """
        def _do_webhook_lookup(webhook_rec):
            res = webhook_rec
            if len(res) == 0:
                raise UnrecognizedCapabilityError(capability_hash, 1)
            res = res[0]
            return (res['tenantId'], res['groupId'], res['policyId'])

        query = _cql_find_webhook_token.format(cf=self.webhooks_table)
        d = self.connection.execute(query,
                                    {"webhookKey": capability_hash},
                                    get_consistency_level('list', 'group'))
        d.addCallback(_do_webhook_lookup)
        return d

    def get_counts(self, log, tenant_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.get_counts`
        """

        fields = ['scaling_group', 'scaling_policies', 'policy_webhooks']
        deferred = [self.connection.execute(_cql_count_for_tenant.format(cf=field),
                                            {'tenantId': tenant_id},
                                            get_consistency_level('count', 'group'))
                    for field in fields]

        d = defer.gatherResults(deferred)
        d.addCallback(lambda results: [r[0]['count'] for r in results])
        d.addCallback(lambda results: dict(zip(
            ('groups', 'policies', 'webhooks'), results)))
        return d

    def health_check(self, clock=None):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.health_check`

        In addition to ``healthy`` and ``time``, returns whether it can
        connect to cassandra and zookeeper
        """
        if clock is None:
            clock = reactor

        if self.kz_client is None:
            zk_health = {'zookeeper': False,
                         'zookeeper_state': 'Not connected yet'}
        elif not self.kz_client.connected:
            zk_health = {'zookeeper': False,
                         'zookeeper_state': 'Not connected yet'}
        else:
            state = self.kz_client.state
            zk_health = {'zookeeper': state == KazooState.CONNECTED,
                         'zookeeper_state': state}

        start_time = clock.seconds()

        d = self.connection.execute(
            _cql_health_check.format(cf=self.group_table), {},
            get_consistency_level('health', 'check'))

        # stop health check after 15 seconds
        timeout_deferred(d, 15, clock=clock,
                         deferred_description='cassandra health check')

        d.addCallback(lambda _: (zk_health['zookeeper'], dict(
            cassandra=True,
            cassandra_time=(clock.seconds() - start_time),
            **zk_health
        )))

        d.addErrback(lambda f: (False, dict(
            cassandra=False,
            cassandra_failure=repr(f.value),
            cassandra_time=clock.seconds() - start_time,
            **zk_health
        )))

        return d


@implementer(IAdmin)
class CassAdmin(object):
    """
    .. autointerface:: otter.models.interface.IAdmin
    """

    def __init__(self, connection):
        self.connection = connection

    def get_metrics(self, log):
        """
        see :meth:`otter.models.interface.IAdmin.get_metrics`
        """
        def _get_metric(table, label):
            """
            Execute a CQL statement and return a formatted result
            """
            def _format_result(result, label):
                """
                :param result: Result from metric collection
                :param label: Label for the metric

                :return: dict of metric label, value and time
                """
                return dict(
                    id="otter.metrics.{0}".format(label),
                    value=result[0]['count'],
                    time=int(time.time()))

            dc = self.connection.execute(_cql_count_all.format(cf=table), {},
                                         get_consistency_level('count', 'group'))
            dc.addCallback(_format_result, label)
            return dc

        tables = ['scaling_group', 'scaling_policies', 'policy_webhooks']
        labels = ['groups', 'policies', 'webhooks']
        mapping = zip(tables, labels)

        deferreds = [_get_metric(table, label) for table, label in mapping]
        return defer.gatherResults(deferreds, consumeErrors=True)
