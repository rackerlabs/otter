"""
 Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError)
import zope.interface

from twisted.internet import defer
from otter.util.cqlbatch import Batch
from otter.util.hashkey import generate_key_str

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


def _build_policies(policies, policies_table, queries, data, outpolicies):
    if policies is not None:
        for i in range(len(policies)):
            polname = "policy{}".format(i)
            polId = generate_key_str('policy')
            queries.append(_cql_insert_policy.format(cf=policies_table,
                                                     name=':' + polname))
            data[polname] = _serial_json_data(policies[i], 1)
            data[polname + "Id"] = polId
            outpolicies[polId] = policies[i]


class CassScalingGroup(object):
    """
    Scaling group record

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
    :type config: ``list``

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

    def __init__(self, tenant_id, uuid, connection):
        """
        Creates a CassScalingGroup object.
        """
        self.tenant_id = tenant_id
        self.uuid = uuid
        self.connection = connection
        self.config_table = "scaling_config"
        self.launch_table = "launch_config"
        self.policies_table = "scaling_policies"

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
        raise NotImplementedError()

    def view_config(self):
        """
        :return: a view of the config, as specified by
            :data:`otter.json_schema.group_schemas.config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        query = _cql_view.format(cf=self.config_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid})
        d.addCallback(self._grab_json_data)
        return d

    def view_launch_config(self):
        """
        :return: a view of the launch config, as specified by
            :data:`otter.json_schema.group_schemas.launch_config`
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with
            ``dict``

        :raises: :class:`NoSuchScalingGroupError` if this scaling group (one
            with this uuid) does not exist
        """
        query = _cql_view.format(cf=self.launch_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid})
        d.addCallback(self._grab_json_data)
        return d

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
        raise NotImplementedError()

    # TODO: There is no state yet, and updating the config should update the
    # state
    def update_config(self, data):
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
        def _do_update_config(lastRev):
            # IMPORTANT REMINDER: lastRev contains the previous
            # state.... but you can't be guaranteed that the
            # previous state hasn't changed between when you
            # got it back from Cassandra and when you are
            # sending your new insert request.
            queries = [_cql_update.format(cf=self.config_table, name=":scaling")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "scaling": _serial_json_data(data, 1)})
            return b.execute(self.connection)

        d = self.view_config()
        d.addCallback(_do_update_config)
        return d

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
        def _do_update_launch(lastRev):
            # IMPORTANT REMINDER: lastRev contains the previous
            # state.... but you can't be guaranteed that the
            # previous state hasn't changed between when you
            # got it back from Cassandra and when you are
            # sending your new insert request.
            queries = [_cql_update.format(cf=self.launch_table, name=":launch")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "launch": _serial_json_data(data, 1)})
            d = b.execute(self.connection)
            return d

        d = self.view_config()
        d.addCallback(_do_update_launch)
        return d

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
        raise NotImplementedError()

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
        raise NotImplementedError()

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
                    if rawRec.get('name', None) is 'policyId':
                        policyId = rawRec.get('value')
                    if rawRec.get('name', None) is 'data':
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
            return defer.succeed(data)

        query = _cql_list_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid})
        d.addCallback(_grab_pol_list)
        return d

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
        query = _cql_view_policy.format(cf=self.policies_table)
        d = self.connection.execute(query,
                                    {"tenantId": self.tenant_id,
                                     "groupId": self.uuid,
                                     "policyId": policy_id})
        d.addCallback(self._grab_json_data)
        return d

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
        def _do_create_pol(lastRev):
            # IMPORTANT REMINDER: lastRev contains the previous
            # state.... but you can't be guaranteed that the
            # previous state hasn't changed between when you
            # got it back from Cassandra and when you are
            # sending your new insert request.

            queries = []
            cqldata = {"tenantId": self.tenant_id,
                       "groupId": self.uuid}
            outpolicies = {}

            _build_policies(data, self.policies_table, queries, cqldata, outpolicies)

            b = Batch(queries, cqldata)
            d = b.execute(self.connection)
            return d.addCallback(lambda _: outpolicies)

        d = self.view_config()
        d.addCallback(_do_create_pol)
        return d

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
        def _do_update_launch(lastRev):
            # IMPORTANT REMINDER: lastRev contains the previous
            # state.... but you can't be guaranteed that the
            # previous state hasn't changed between when you
            # got it back from Cassandra and when you are
            # sending your new insert request.
            queries = [_cql_update_policy.format(cf=self.policies_table, name=":policy")]

            b = Batch(queries, {"tenantId": self.tenant_id,
                                "groupId": self.uuid,
                                "policyId": policy_id,
                                "policy": _serial_json_data(data, 1)})
            d = b.execute(self.connection)
            return d

        d = self.get_policy(policy_id)
        d.addCallback(_do_update_launch)
        d.addCallback(lambda _: data)
        return d

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
        queries = [
            _cql_delete_policy.format(cf=self.policies_table)]
        b = Batch(
            queries, {"tenantId": self.tenant_id,
                      "groupId": self.uuid,
                      "policyId": policy_id})
        return b.execute(self.connection)

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
        raise NotImplementedError()

    def create_webhooks(self, policy_id, data):
        """
        Creates a new capability URL for one particular scaling policy

        :param policy_id: the uuid of the policy to be deleted
        :type policy_id: ``str``

        :param data: a list of details of the webhook in JSON format, as specified
            by :data:`otter.json_schema.group_schemas.webhook`
        :type data: ``dict``

        :return: a :class:`twisted.internet.defer.Deferred` that fires with None

        :raises: :class:`NoSuchPolicyError` if the policy id does not exist
        """
        raise NotImplementedError()

    def _grab_json_data(self, rawResponse):
        if rawResponse is None:
            raise CassBadDataError("received unexpected None response")
        if len(rawResponse) == 0:
            raise NoSuchScalingGroupError(self.tenant_id, self.uuid)
        if 'cols' not in rawResponse[0]:
            raise CassBadDataError("Received malformed response with no cols")
        rec = None
        for rawRec in rawResponse[0].get('cols', []):
            if rawRec.get('name', None) is 'data':
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
    Scaling group collections

    The structure..

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

    def create_scaling_group(self, tenant_id, config, launch, policies=None):
        """
        Create scaling group based on the tenant id, the configuration
        paramaters, the launch config, and optional scaling policies.

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
        _build_policies(policies, self.policies_table, queries, data, outpolicies)

        b = Batch(queries, data)
        d = b.execute(self.connection)
        d.addCallback(lambda _: scaling_group_id)
        return d

    def delete_scaling_group(self, tenant_id, scaling_group_id):
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
        def _delete_it(lastRev):
            # IMPORTANT REMINDER: lastRev contains the previous
            # state.... but you can't be guaranteed that the
            # previous state hasn't changed between when you
            # got it back from Cassandra and when you are
            # sending your new insert request.
            queries = [
                _cql_delete.format(cf=self.config_table),
                _cql_delete.format(cf=self.launch_table),
                _cql_delete.format(cf=self.policies_table)]
            b = Batch(
                queries, {"tenantId": tenant_id, "groupId": scaling_group_id})
            return b.execute(self.connection)

        group = self.get_scaling_group(tenant_id, scaling_group_id)
        d = group.view_config()  # ensure that it's actually there
        return d.addCallback(_delete_it)  # only delete if it exists

    def list_scaling_groups(self, tenant_id):
        """
        List the scaling groups for this tenant ID

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: a list of scaling groups
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            ``list`` of :class:`IScalingGroup` providers
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
                    if rawRec.get('name', None) is 'groupId':
                        rec = rawRec.get('value', None)
                if rec is None:
                    raise CassBadDataError("Received malformed response without the "
                                           "required fields")
                data.append(CassScalingGroup(tenant_id, rec,
                                             self.connection))
            return data

        query = _cql_list.format(cf=self.config_table)
        d = self.connection.execute(query,
                                    {"tenantId": tenant_id})
        d.addCallback(_grab_list)
        return d

    def get_scaling_group(self, tenant_id, scaling_group_id):
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
        return CassScalingGroup(tenant_id, scaling_group_id,
                                self.connection)

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
