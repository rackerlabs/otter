"""
Cassandra implementation of the store for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchPolicyError)
import zope.interface

from twisted.internet import defer
from otter.util.cqlbatch import Batch
from otter.util.hashkey import generate_capability, generate_key_str

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


_cql_view = ('SELECT data FROM {cf} WHERE "tenantId" = :tenantId AND '
             '"groupId" = :groupId AND deleted = False;')
_cql_view_policy = ('SELECT data FROM {cf} WHERE "tenantId" = :tenantId AND '
                    '"groupId" = :groupId AND "policyId" = :policyId AND deleted = False;')
_cql_insert = ('INSERT INTO {cf}("tenantId", "groupId", data, deleted) '
               'VALUES (:tenantId, :groupId, {name}, False)')
_cql_insert_policy = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", data, deleted) '
                      'VALUES (:tenantId, :groupId, {name}Id, {name}, False)')
_cql_insert_webhook = (
    'INSERT INTO {cf}("tenantId", "groupId", "policyId", "webhookId", data, "webhookKey", deleted) '
    'VALUES (:tenantId, :groupId, :policyId, :{name}Id, :{name}, :{name}Key, False)')
_cql_update = ('INSERT INTO {cf}("tenantId", "groupId", data) '
               'VALUES (:tenantId, :groupId, {name})')
_cql_update_policy = ('INSERT INTO {cf}("tenantId", "groupId", "policyId", data) '
                      'VALUES (:tenantId, :groupId, {name}Id, {name})')
_cql_delete = 'UPDATE {cf} SET deleted=True WHERE "tenantId" = :tenantId AND "groupId" = :groupId'
_cql_delete_policy = ('UPDATE {cf} SET deleted=True WHERE "tenantId" = :tenantId '
                      'AND "groupId" = :groupId AND "policyId" = :policyId')
_cql_list = 'SELECT "groupId" FROM {cf} WHERE "tenantId" = :tenantId AND deleted = False;'
_cql_list_policy = ('SELECT "policyId", data FROM {cf} WHERE "tenantId" = :tenantId AND '
                    '"groupId" = :groupId AND deleted = False;')


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
    for i in range(len(bare_webhooks)):
        name = "webhook{0}".format(i)
        webhook_id = generate_key_str('webhook')
        webhook_cap = generate_capability(webhook_id)
        queries.append(_cql_insert_webhook.format(cf=webhooks_table,
                                                  name=name))

        # generate the real data that will be stored, which includes the webhook
        # token, the capability stuff, and metadata by default
        # TODO: capability format should change so that multiple capability
        #       hash versions can be stored
        webhook_real = {'metadata': {}, 'capability': {}}
        webhook_real.update(bare_webhooks[i])
        (token, webhook_real['capability']['hash'],
            webhook_real['capability']['version']) = webhook_cap

        cql_parameters[name] = _serial_json_data(webhook_real, 1)
        cql_parameters['{0}Id'.format(name)] = webhook_id
        cql_parameters['{0}Key'.format(name)] = webhook_cap[1]
        output[webhook_id] = webhook_real


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

    def set_steady_state(self, steady_state):
        """
        see :meth:`otter.models.interface.IScalingGroup.set_steady_state`
        """
        raise NotImplementedError()

    def bounce_entity(self, entity_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.bounce_entity`
        """
        raise NotImplementedError()

    def list_policies(self):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_policies`
        """
        def _grab_pol_list(rawResponse):
            if rawResponse is None:
                raise CassBadDataError("received unexpected None response")
            data = {}
            for row in rawResponse:
                if 'cols' not in row:
                    raise CassBadDataError("Received malformed response with no cols")
                rec = None
                policyId = None
                for rawRec in row['cols']:
                    if rawRec.get('name', None) == 'policyId':
                        policyId = rawRec.get('value')
                    if rawRec.get('name', None) == 'data':
                        rec = rawRec.get('value')
                if rec is None or policyId is None:
                    raise CassBadDataError("Received malformed response without the "
                                           "required fields")
                try:
                    data[policyId] = json.loads(rec)
                    if "_ver" in data[policyId]:
                        del data[policyId]["_ver"]
                except ValueError:
                    raise CassBadDataError("Bad data in database")

            if len(data) == 0:
                # If there is no data - make sure it's not because the group
                # doesn't exist
                return self.view_config().addCallback(lambda _: data)
            return defer.succeed(data)

        query = _cql_list_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid},
                                    get_consistency_level('list', 'policy'))
        d.addCallback(_grab_pol_list)
        return d

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

    def delete_policy(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_policy`
        """
        def _do_delete_policy(lastRev):
            queries = [
                _cql_delete_policy.format(cf=self.policies_table)]
            b = Batch(
                queries, {"tenantId": self.tenant_id,
                          "groupId": self.uuid,
                          "policyId": policy_id},
                consistency=get_consistency_level('delete', 'policy'))

            return b.execute(self.connection)

        d = self.get_policy(policy_id)
        d.addCallback(_do_delete_policy)
        d.addCallback(lambda _: None)
        return d

    def list_webhooks(self, policy_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.list_webhooks`
        """
        raise NotImplementedError()

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
        raise NotImplementedError()

    def update_webhook(self, policy_id, webhook_id, data):
        """
        see :meth:`otter.models.interface.IScalingGroup.update_webhook`
        """
        raise NotImplementedError()

    def delete_webhook(self, policy_id, webhook_id):
        """
        see :meth:`otter.models.interface.IScalingGroup.delete_webhook`
        """
        raise NotImplementedError()

    def _grab_json_data(self, rawResponse, policy_id=None):
        if rawResponse is None:
            raise CassBadDataError("received unexpected None response")
        if len(rawResponse) == 0:
            if not policy_id:
                raise NoSuchScalingGroupError(self.tenant_id, self.uuid)
            else:
                raise NoSuchPolicyError(self.tenant_id, self.uuid, policy_id)
        if 'cols' not in rawResponse[0]:
            raise CassBadDataError("Received malformed response with no cols")
        rec = None
        for rawRec in rawResponse[0].get('cols', []):
            if rawRec.get('name', None) == 'data':
                rec = rawRec.get('value', None)
        if rec is None:
            raise CassBadDataError("Received malformed response without the "
                                   "required fields")
        data = None
        try:
            data = json.loads(rec)
            if "_ver" in data:
                del data["_ver"]
            return data
        except ValueError:
            raise CassBadDataError("Bad data")


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
        def _delete_it(lastRev):
            queries = [
                _cql_delete.format(cf=self.config_table),
                _cql_delete.format(cf=self.launch_table),
                _cql_delete.format(cf=self.policies_table)]
            b = Batch(
                queries, {"tenantId": tenant_id, "groupId": scaling_group_id},
                consistency=get_consistency_level('delete', 'group'))
            return b.execute(self.connection)

        group = self.get_scaling_group(log, tenant_id, scaling_group_id)
        d = group.view_config()  # ensure that it's actually there
        return d.addCallback(_delete_it)  # only delete if it exists

    def list_scaling_groups(self, log, tenant_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.list_scaling_groups`
        """
        def _grab_list(rawResponse):
            if rawResponse is None:
                raise CassBadDataError("received unexpected None response")
            if len(rawResponse) == 0:
                return defer.succeed([])
            data = []
            for row in rawResponse:
                if 'cols' not in row:
                    raise CassBadDataError("Received malformed response with no cols")
                rec = None
                for rawRec in row.get('cols', []):
                    if rawRec.get('name', None) == 'groupId':
                        rec = rawRec.get('value', None)
                if rec is None:
                    raise CassBadDataError("Received malformed response without the "
                                           "required fields")
                data.append(CassScalingGroup(log, tenant_id, rec,
                                             self.connection))
            return data

        query = _cql_list.format(cf=self.config_table)
        d = self.connection.execute(query,
                                    {"tenantId": tenant_id},
                                    get_consistency_level('list', 'group'))
        d.addCallback(_grab_list)
        return d

    def get_scaling_group(self, log, tenant_id, scaling_group_id):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.get_scaling_group`
        """
        return CassScalingGroup(log, tenant_id, scaling_group_id,
                                self.connection)

    def execute_webhook(self, capability_hash):
        """
        see :meth:`otter.models.interface.IScalingGroupCollection.execute_webhook`
        """
        raise NotImplementedError()
