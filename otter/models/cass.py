"""
Cassandra implementation of the store for the front-end scaling groups engine
"""
import zope.interface

from twisted.internet import defer

from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchPolicyError,
                                    NoSuchWebhookError, UnrecognizedCapabilityError)
from otter.util.cqlbatch import Batch
from otter.util.hashkey import generate_capability, generate_key_str
#from otter.controller import maybe_execute_scaling_policy

from silverberg.client import ConsistencyLevel

import json


class CassBadDataError(Exception):
    """
    Error to be raised when attempting operations on an entity that does not
    exist.
    """
    pass


def _serial_json_data(data, ver):
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
_cql_view = ('SELECT data FROM {cf} WHERE "tenantId" = :tenantId AND '
             '"groupId" = :groupId AND deleted = False;')
_cql_view_policy = ('SELECT data FROM {cf} WHERE "tenantId" = :tenantId AND '
                    '"groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
_cql_view_webhook = ('SELECT data, capability FROM {cf} WHERE "tenantId" = :tenantId AND '
                     '"groupId" = :groupId AND "policyId" = :policyId AND '
                     '"webhookId" = :webhookId AND deleted = False;')
_cql_insert = ('INSERT INTO {cf}("tenantId", "groupId", data, deleted) '
               'VALUES (:tenantId, :groupId, {name}, False)')
_cql_insert_policy = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", data, deleted) '
                      'VALUES (:tenantId, :groupId, {name}Id, {name}, False)')
_cql_insert_webhook = (
    'INSERT INTO {cf}("tenantId", "groupId", "policyId", "webhookId", data, capability, '
    '"webhookKey", deleted) VALUES (:tenantId, :groupId, :policyId, :{name}Id, :{name}, '
    ':{name}Capability, :{name}Key, False)')
_cql_update = ('INSERT INTO {cf}("tenantId", "groupId", data) '
               'VALUES (:tenantId, :groupId, {name})')
_cql_update_policy = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", data) '
                      'VALUES (:tenantId, :groupId, {name}Id, {name})')
_cql_update_webhook = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", "webhookId", data) '
                       'VALUES (:tenantId, :groupId, :policyId, :webhookId, :data);')
_cql_delete = 'UPDATE {cf} SET deleted=True WHERE "tenantId" = :tenantId AND "groupId" = :groupId'
_cql_delete_policy = ('UPDATE {cf} SET deleted=True WHERE "tenantId" = :tenantId '
                      'AND "groupId" = :groupId AND "policyId" = {name}')
_cql_delete_webhook = ('UPDATE {cf} SET deleted=True WHERE "tenantId" = :tenantId '
                       'AND "groupId" = :groupId AND "policyId" = :policyId AND '
                       '"webhookId" = :{name}')
_cql_list = 'SELECT "groupId" FROM {cf} WHERE "tenantId" = :tenantId AND deleted = False;'
_cql_list_policy = ('SELECT "policyId", data FROM {cf} WHERE "tenantId" = :tenantId AND '
                    '"groupId" = :groupId AND deleted = False;')
_cql_list_webhook = ('SELECT "webhookId", data, capability FROM {cf} WHERE "tenantId" = :tenantId AND '
                     '"groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
_cql_find_webhook_token = ('SELECT "tenantId", "groupId", "policyId", deleted FROM {cf} WHERE '
                           '"webhookKey" = :webhookKey;')


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
    return ConsistencyLevel.ONE


def _build_policies(policies, policies_table, queries, data, outpolicies):
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

    :param outpolicies: a dictionary to which to insert the created policies
        along with their generated IDs
    :type outpolicies: ``dict``
    """
    if policies is not None:
        for i in range(len(policies)):
            polname = "policy{}".format(i)
            polId = generate_key_str('policy')
            queries.append(_cql_insert_policy.format(cf=policies_table,
                                                     name=':' + polname))
            data[polname] = _serial_json_data(policies[i], 1)
            data[polname + "Id"] = polId
            outpolicies[polId] = policies[i]


def _build_webhooks(bare_webhooks, webhooks_table, queries, cql_parameters,
                    output):
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

    :param output: a dictionary to which to insert the created policies
        along with their generated IDs
    :type output: ``dict``
    """
    for i, webhook in enumerate(bare_webhooks):
        name = "webhook{0}".format(i)
        webhook_id = generate_key_str('webhook')
        queries.append(_cql_insert_webhook.format(cf=webhooks_table,
                                                  name=name))

        # generate the real data that will be stored, which includes the webhook
        # token, the capability stuff, and metadata by default
        bare_webhooks[i].setdefault('metadata', {})
        version, cap_hash = generate_capability()

        cql_parameters[name] = _serial_json_data(webhook, 1)
        cql_parameters['{0}Id'.format(name)] = webhook_id
        cql_parameters['{0}Key'.format(name)] = cap_hash
        cql_parameters['{0}Capability'.format(name)] = _serial_json_data(
            {version: cap_hash}, 1)

        output[webhook_id] = webhook.copy()
        output[webhook_id]['capability'] = {'hash': cap_hash, 'version': version}


def _assemble_webhook_from_row(row):
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

    return webhook_base


def _jsonize_cassandra_data(raw_response):
    """
    Unwrap cassandra responses into an array of dicts - this should probably
    go into silverberg.

    :param dict raw_response: the raw response from Cassandra

    :return: ``list`` of ``dicts`` representing the Cassandra data
    """
    if raw_response is None:
        raise CassBadDataError("Received unexpected None response")

    results = []
    for row in raw_response:
        if 'cols' not in row:
            raise CassBadDataError("Received malformed response with no cols")
        try:
            results.append({col['name']: col['value'] for col in row['cols']})
        except KeyError as e:
            raise CassBadDataError('Received malformed response without the '
                                   'required field "{0!s}"'.format(e))

    return results


def _unwrap_one_row(raw_response):
    """
    Unwrap a row into a dict - None is an acceptable raw response
    """
    if raw_response is None:
        return None

    if len(raw_response) != 1:
        raise CassBadDataError("multiple responses when we expected 1")

    results = _jsonize_cassandra_data(raw_response)
    return results[0]


def _jsonloads_data(raw_data):
    try:
        data = json.loads(raw_data)
    except ValueError:
        raise CassBadDataError("Bad data in database - not JSON")
    else:
        if "_ver" in data:
            del data["_ver"]
        return data


def _grab_list(raw_response, id_name, has_data=True):
    """
    The response is a list of stuff.  Return the list.

    :param raw_response: the raw response from cassandra
    :type raw_response: ``dict``

    :param id_name: The column name to look for and get
    :type id_name: ``str``

    :param has_data: Whether to pull a data object out or not.  Determines
        whether the returned value is a list or a dictionary
    :type has_data: ``bool``

    :return: a ``list`` or ``dict`` representing the data in Cassandra
    """
    results = _jsonize_cassandra_data(raw_response)
    try:
        if has_data:
            return dict([(row[id_name], _jsonloads_data(row['data']))
                         for row in results])
        else:
            return [row[id_name] for row in results]
    except KeyError as e:
        raise CassBadDataError('Received malformed response without the '
                               'required field "{0!s}"'.format(e))


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
    zope.interface.implements(IScalingGroup)

    def __init__(self, log, tenant_id, uuid, connection):
        """
        Creates a CassScalingGroup object.
        """
        self.log = log.name(self.__class__.__name__)
        self.tenant_id = tenant_id
        self.uuid = uuid
        self.connection = connection
        self.config_table = "scaling_config"
        self.launch_table = "launch_config"
        self.policies_table = "scaling_policies"
        self.webhooks_table = "policy_webhooks"

    def view_manifest(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_manifest`
        """
        raise NotImplementedError()

    def view_config(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_config`
        """
        query = _cql_view.format(cf=self.config_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid},
                                    get_consistency_level('view', 'partial'))
        d.addCallback(self._grab_json_data)
        return d

    def view_launch_config(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_launch_config`
        """
        query = _cql_view.format(cf=self.launch_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid},
                                    get_consistency_level('view', 'partial'))
        d.addCallback(self._grab_json_data)
        return d

    def view_state(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.view_state`
        """
        raise NotImplementedError()

    # TODO: There is no state yet, and updating the config should update the
    # state
    def update_config(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_config`
        """
        def _do_update_config(lastRev):
            queries = [_cql_update.format(cf=self.config_table, name=":scaling")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "scaling": _serial_json_data(data, 1)},
                      consistency=get_consistency_level('update', 'partial'))
            return b.execute(self.connection)

        d = self.view_config()
        d.addCallback(_do_update_config)
        return d

    def update_launch_config(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_launch_config`
        """
        def _do_update_launch(lastRev):
            queries = [_cql_update.format(cf=self.launch_table, name=":launch")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "launch": _serial_json_data(data, 1)},
                      consistency=get_consistency_level('update', 'partial'))
            d = b.execute(self.connection)
            return d

        d = self.view_config()
        d.addCallback(_do_update_launch)
        return d

    def _naive_list_policies(self):
        """
        Like :meth:`otter.models.cass.CassScalingGroup.list_policies`, but gets
        all the policies associated with particular scaling group
        irregardless of whether the scaling group still exists.
        """
        query = _cql_list_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid},
                                    get_consistency_level('list', 'policy'))
        d.addCallback(_grab_list, 'policyId', has_data=True)
        return d

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
        # If there are no policies - make sure it's not because the group
        # doesn't exist
        def _check_if_empty(policies_dict):
            if len(policies_dict) == 0:
                return self.view_config().addCallback(lambda _: policies_dict)
            return policies_dict

        d = self._naive_list_policies()
        return d.addCallback(_check_if_empty)

    def get_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.get_policy`
        """
        query = _cql_view_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid,
                                     "policyId": policy_id},
                                    get_consistency_level('view', 'policy'))
        d.addCallback(self._grab_json_data, policy_id)
        return d

    def create_policies(self, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.create_policies`
        """
        def _do_create_pol(lastRev):
            queries = []
            cqldata = {"tenantId": self.tenant_id,
                       "groupId": self.uuid}
            outpolicies = {}

            _build_policies(data, self.policies_table, queries, cqldata,
                            outpolicies)

            b = Batch(queries, cqldata,
                      consistency=get_consistency_level('create', 'policy'))
            d = b.execute(self.connection)
            return d.addCallback(lambda _: outpolicies)

        d = self.view_config()
        d.addCallback(_do_create_pol)
        return d

    def update_policy(self, policy_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_policy`
        """
        def _do_update_launch(lastRev):
            queries = [_cql_update_policy.format(cf=self.policies_table, name=":policy")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "policyId": policy_id,
                                "policy": _serial_json_data(data, 1)},
                      consistency=get_consistency_level('update', 'policy'))
            d = b.execute(self.connection)
            return d

        d = self.get_policy(policy_id)
        d.addCallback(_do_update_launch)
        return d

    def _naive_delete_policy(self, policy_id, consistency):
        """
        Like :meth:`otter.models.cass.CassScalingGroup.delete_policy` but
        does not check if the policy exists first before deleting it.  Assumes
        that it does exist.
        """
        def _do_delete_policy():
            queries = [
                _cql_delete_policy.format(cf=self.policies_table,
                                          name=":policyId")]
            b = Batch(
                queries, {"tenantId": self.tenant_id,
                          "groupId": self.uuid,
                          "policyId": policy_id},
                consistency=consistency)
            return b.execute(self.connection)

        def _do_delete_webhooks(webhook_dict):
            if len(webhook_dict) == 0:  # don't hit cassandra at all
                return defer.succeed(None)

            queries = []
            cql_params = {'tenantId': self.tenant_id, 'groupId': self.uuid,
                          'policyId': policy_id}

            for i, webhook_id in enumerate(webhook_dict.keys()):
                varname = 'webhookId{0}'.format(i)
                queries.append(_cql_delete_webhook.format(
                    cf=self.webhooks_table, name=varname))
                cql_params[varname] = webhook_id

            b = Batch(queries, cql_params, consistency=consistency)
            return b.execute(self.connection)

        return defer.gatherResults(
            [_do_delete_policy(),
             self._naive_list_webhooks(policy_id).addCallback(_do_delete_webhooks)])

    def delete_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_policy`
        """
        d = self.get_policy(policy_id)
        d.addCallback(lambda _: self._naive_delete_policy(
            policy_id, get_consistency_level('delete', 'policy')))
        d.addCallback(lambda _: None)
        return d

    def execute_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.execute_policy`
        """
        def _do_stuff(pol):
            # Doing stuff will go here.
            #maybe_execute_scaling_policy(self.log, None, self, pol)
            return None

        d = self.get_policy(policy_id)
        d.addCallback(_do_stuff)

    def _naive_list_webhooks(self, policy_id):
        """
        Like :meth:`otter.models.cass.CassScalingGroup.list_webhooks`, but gets
        all the webhooks associated with particular scaling policy
        irregardless of whether the scaling policy still exists.
        """
        def _assemble_webhook_results(results):
            new_results = {}
            for row in results:
                try:
                    new_results[row['webhookId']] = _assemble_webhook_from_row(row)
                except KeyError as e:
                    raise CassBadDataError('Received malformed response without the '
                                           'required field "{0!s}"'.format(e))

            return new_results

        query = _cql_list_webhook.format(cf=self.webhooks_table)
        d = self.connection.execute(query, {"tenantId": self.tenant_id,
                                            "groupId": self.uuid,
                                            "policyId": policy_id},
                                    get_consistency_level('list', 'webhook'))
        d.addCallback(_jsonize_cassandra_data)
        d.addCallback(_assemble_webhook_results)
        return d

    def list_webhooks(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_webhooks`
        """
        def _check_if_empty(webhooks_dict):
            if len(webhooks_dict) == 0:
                policy_there = self.get_policy(policy_id)
                return policy_there.addCallback(lambda _: webhooks_dict)
            return webhooks_dict

        d = self._naive_list_webhooks(policy_id)
        d.addCallback(_check_if_empty)
        return d

    def create_webhooks(self, policy_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.create_webhooks`
        """
        def _do_create(lastRev):
            queries = []
            cql_params = {"tenantId": self.tenant_id,
                          "groupId": self.uuid,
                          "policyId": policy_id}
            output = {}

            _build_webhooks(data, self.webhooks_table, queries, cql_params,
                            output)

            b = Batch(queries, cql_params,
                      consistency=get_consistency_level('create', 'webhook'))
            d = b.execute(self.connection)
            return d.addCallback(lambda _: output)

        d = self.get_policy(policy_id)  # check that policy exists first
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
            try:
                return _assemble_webhook_from_row(cass_data[0])
            except KeyError as e:
                raise CassBadDataError('Received malformed response without the '
                                       'required field "{0!s}"'.format(e))

        query = _cql_view_webhook.format(cf=self.webhooks_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid,
                                     "policyId": policy_id,
                                     "webhookId": webhook_id},
                                    get_consistency_level('view', 'webhook'))
        d.addCallback(_jsonize_cassandra_data)
        d.addCallback(_assemble_webhook)
        return d

    def update_webhook(self, policy_id, webhook_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_webhook`
        """
        def _update_data(lastRev):
            data.setdefault('metadata', {})
            query = _cql_update_webhook.format(cf=self.webhooks_table)
            d = self.connection.execute(query,
                                        {"tenantId": self.tenant_id,
                                         "groupId": self.uuid,
                                         "policyId": policy_id,
                                         "webhookId": webhook_id,
                                         "data": data},
                                        get_consistency_level('update', 'webhook'))
            return d

        d = self.get_webhook(policy_id, webhook_id)
        return d.addCallback(_update_data)

    def delete_webhook(self, policy_id, webhook_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_webhook`
        """
        def _do_delete(lastRev):
            query = _cql_delete_webhook.format(
                cf=self.webhooks_table, name="webhookId")

            d = self.connection.execute(query,
                                        {"tenantId": self.tenant_id,
                                         "groupId": self.uuid,
                                         "policyId": policy_id,
                                         "webhookId": webhook_id},
                                        get_consistency_level('delete', 'webhook'))
            return d

        return self.get_webhook(policy_id, webhook_id).addCallback(_do_delete)

    def _grab_json_data(self, rawResponse, policy_id=None, webhook_id=None):
        results = _jsonize_cassandra_data(rawResponse)
        if len(results) == 0:
            if webhook_id is not None:
                raise NoSuchWebhookError(self.tenant_id, self.uuid, policy_id,
                                         webhook_id)
            elif policy_id is not None:
                raise NoSuchPolicyError(self.tenant_id, self.uuid, policy_id)
            else:
                raise NoSuchScalingGroupError(self.tenant_id, self.uuid)

        elif len(results) > 1:
            raise CassBadDataError("Recieved more than one expected response")

        if 'data' not in results[0]:
            raise CassBadDataError('Received malformed response without the '
                                   'required field "data"')

        return _jsonloads_data(results[0]['data'])


class CassScalingGroupCollection:
    """
    .. autointerface:: otter.models.interface.IScalingGroupCollection

    The Cassandra schema structure::

        Configs:
        CF = scaling_config
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
    zope.interface.implements(IScalingGroupCollection)

    def __init__(self, connection):
        """
        Init

        :param connection: Thrift connection to use

        :param cflist: Column family list
        """
        self.connection = connection
        self.config_table = "scaling_config"
        self.launch_table = "launch_config"
        self.policies_table = "scaling_policies"
        self.webhooks_table = "policy_webhooks"

    def create_scaling_group(self, log, tenant_id, config, launch, policies=None):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.create_scaling_group`
        """
        scaling_group_id = generate_key_str('scalinggroup')

        queries = [
            _cql_insert.format(cf=self.config_table, name=":scaling"),
            _cql_insert.format(cf=self.launch_table, name=":launch")]

        data = {"tenantId": tenant_id,
                "groupId": scaling_group_id,
                "scaling": _serial_json_data(config, 1),
                "launch": _serial_json_data(launch, 1),
                }

        outpolicies = {}
        _build_policies(policies, self.policies_table, queries, data,
                        outpolicies)

        b = Batch(queries, data,
                  consistency=get_consistency_level('create', 'group'))
        d = b.execute(self.connection)
        d.addCallback(lambda _: scaling_group_id)
        return d

    def delete_scaling_group(self, log, tenant_id, scaling_group_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.delete_scaling_group`
        """
        consistency = get_consistency_level('delete', 'group')

        def _delete_configs():
            queries = [
                _cql_delete.format(cf=self.config_table),
                _cql_delete.format(cf=self.launch_table),
            ]
            b = Batch(queries,
                      {"tenantId": tenant_id, "groupId": scaling_group_id},
                      consistency=consistency)
            return b.execute(self.connection)

        def _delete_policies(policy_dict, group):  # CassScalingGroup.list_policies
            if len(policy_dict) == 0:
                return

            deferreds = []
            for policy_id in policy_dict:
                deferreds.append(group._naive_delete_policy(policy_id, consistency))
            return defer.gatherResults(deferreds)

        def _delete_it(lastRev, group):
            d = defer.gatherResults([
                _delete_configs(),
                group._naive_list_policies().addCallback(_delete_policies, group)
            ])
            d.addCallback(lambda _: None)
            return d

        group = self.get_scaling_group(log, tenant_id, scaling_group_id)
        d = group.view_config()  # ensure that it's actually there
        return d.addCallback(_delete_it, group)  # only delete if it exists

    def list_scaling_groups(self, log, tenant_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.list_scaling_groups`
        """
        def _build_cass_groups(group_ids):
            return [CassScalingGroup(log, tenant_id, group_id, self.connection)
                    for group_id in group_ids]
        query = _cql_list.format(cf=self.config_table)
        d = self.connection.execute(query,
                                    {"tenantId": tenant_id},
                                    get_consistency_level('list', 'group'))
        d.addCallback(_grab_list, 'groupId', has_data=False)
        d.addCallback(_build_cass_groups)
        return d

    def get_scaling_group(self, log, tenant_id, scaling_group_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.get_scaling_group`
        """
        return CassScalingGroup(log, tenant_id, scaling_group_id,
                                self.connection)

    def execute_webhook_hash(self, log, capability_hash):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.execute_webhook_hash`

        Note: We have to post-filter deleted items because of the way that Cassandra works

        Cassandra has a notion of a 'primary key' that you use to look up a record.  It behooves
        you to construct your data in such a way that it can always look up a primary key
        (or, for that matter, a secondary index).  CQL3 lets you create a secondary index, but
        only on one key at a time.... because they realized that everybody using the previous
        version of CQL was spending bunches of time writing code to generate these secondary
        indicies.

        Furthermore, Cassandra doesn't have a proper query planner like a real SQL database,
        so it doesn't actually have any way to determine which index to query first.

        We have two secondary indicies.  One for finding the non-deleted records, one for
        finding the records by capability_hash.  And we can only use one of them at a time.
        It's more efficient for us to use the index that maps from the capability_hash to
        the row instead of the index that picks out what has not been deleted.
        """
        def _do_webhook_lookup(webhook_rec):
            res = _unwrap_one_row(webhook_rec)
            if res is None:
                raise UnrecognizedCapabilityError(capability_hash, 1)
            if res['deleted'] is True:
                raise UnrecognizedCapabilityError(capability_hash, 1)
            group = self.get_scaling_group(log, res['tenantId'], res['groupId'])
            return group.execute_policy(res['policyId'])

        query = _cql_find_webhook_token.format(cf=self.webhooks_table)
        d = self.connection.execute(query,
                                    {"webhookKey": capability_hash},
                                    get_consistency_level('list', 'group'))
        d.addCallback(_do_webhook_lookup)
        return d
