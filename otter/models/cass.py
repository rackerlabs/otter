"""
 Mock interface for the front-end scaling groups engine
"""
from otter.models.interface import (IScalingGroup, IScalingGroupCollection,
                                    NoSuchScalingGroupError, NoSuchEntityError)
import zope.interface

from twisted.internet import defer
from otter.util.cqlbatch import Batch
from otter.util.hashkey import generate_random_str

import json

class CassBadDataError(Exception):
    """
    Error to be raised when attempting operations on an entity that does not
    exist.
    """
    pass


class CassScalingGroup:
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
    
    def __init__(self, tenant_id, uuid, connection, cflist):
        """
        Creates a MockScalingGroup object.  If the actual scaling group should
        be created, a creation argument is provided containing the config, the
        launch config, and optional scaling policies.
        """
        self.tenant_id = tenant_id
        self.uuid = uuid
        self.connection = connection
        self.cflist = cflist
    
    def view_manifest(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        pass

    def view_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the config
        """
        query = "SELECT data FROM scaling_config ";
        varcl = "WHERE accountId = :accountId AND groupId = :groupId"
        d = self.connection.execute(query + varcl + ";",
                                       {"accountId": self.tenant_id, 
                                        "groupId" : self.uuid})
        d.addCallback(self._grab_json_data)
        return d
        
    def view_launch_config(self):
        """
        :return: :class:`Deferred` that fires with a view of the launch config
        """
        query = "SELECT data FROM launch_config ";
        varcl = "WHERE accountId = :accountId AND groupId = :groupId"
        d = self.connection.execute(query + varcl + ";",
                                       {"accountId": self.tenant_id, 
                                        "groupId" : self.uuid})
        d.addCallback(self._grab_json_data)
        return d

    def view_state(self):
        """
        :return: :class:`Deferred` that fires with a view of the state
        """
        pass
 
    def update_config(self, data, partial_update=False):
        """
        Update the scaling group configuration paramaters based on the
        attributes in ``data``.  Has the option to partially update the config,
        since when creating the model there could be default variables.

        :return: :class:`Deferred` that fires with None
        """
        pass

    def update_launch_config(self, data):
        """
        Update the launch config parameters based on the attributes in
        ``data``.  Overwrites the existing launch config.  Note - no error
        checking here happens, so it's possible to get the launch config into
        an improper state.
        """
        pass

    def set_steady_state(self, steady_state):
        """
        Sets the steady state value

        :param steady_state: value to set the steady state to, but will not set
            to anything below the minimum or above the maximum
        :type steady_state: ``int``

        :return: :class:`Deferred` that fires with None
        """
        pass

    def bounce_entity(self, entity_id):
        """
        Rebuilds a entity given by the server ID

        :return: :class:`Deferred` that fires with None
        """
        pass

    def _grab_json_data(self, rawResponse):
        if len(rawResponse) == 0:
            err = NoSuchScalingGroupError(self.tenant_id, self.uuid)
            return defer.fail(err)
        if 'cols' not in rawResponse[0]:
            err = CassBadDataError("No cols")
            return defer.fail(err)
        rec = None
        for rawRec in rawResponse[0]['cols']:
            if rawRec['name'] is 'data':
                rec = rawRec['value']
        if rec is None:
            err = CassBadDataError("No data")
            return defer.fail(err)
        data = None
        try:
            data = json.loads(rec)
            return defer.succeed(data)
        except ValueError:
            err = CassBadDataError("Bad data")
            return defer.fail(err)
    
class CassScalingGroupCollection:
    """
    Scaling group collections

    The structure..

    Configs:
    CF = scaling_config
    RK = accountID
    CK = groupID

    Launch Configs (mirrors config):
    CF = launch_config
    RK = accountID
    CK = groupID

    Scaling Policies (doesn't mirror config):
    CF = policies
    RK = accountID
    CK = groupID:polID
    """
    zope.interface.implements(IScalingGroupCollection)

    def __init__(self, connection, cflist):
        """
        Init

        :param connection: Thrift connection to use

        :param cflist: Column family list
        """
        self.connection = connection
        self.cflist = cflist
        
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
        
        scaling_group_id = generate_random_str(10)
        
        queries = [
                   "INSERT INTO scaling_config(accountId, groupId, data) VALUES (:accountId, :groupId, :scaling)",
                   "INSERT INTO launch_config(accountId, groupId, data) VALUES (:accountId, :groupId, :launch)"]
        b = Batch(queries, {"accountId": tenant_id, 
                            "groupId" : scaling_group_id,
                            "scaling" : config,
                            "launch" : launch,
                            })
        d = b.execute(self.connection);
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
        
        varcl = "WHERE accountId = :accountId AND groupId = :groupId"
                
        queries = [
                   "DELETE FROM scaling_config " + varcl,
                   "DELETE FROM launch_config " + varcl,
                   "DELETE FROM scaling_policies " + varcl]
        b = Batch(queries, {"accountId": tenant_id, "groupId" :scaling_group_id})
        b.execute(self.connection);
        
    def list_scaling_groups(self, tenant_id):
        """
        List the scaling groups for this tenant ID

        :param tenant_id: the tenant ID of the scaling groups
        :type tenant_id: ``str``

        :return: a list of scaling groups
        :rtype: a :class:`twisted.internet.defer.Deferred` that fires with a
            ``list`` of :class:`IScalingGroup` providers
        """
        pass

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
                                self.connection, self.cflist)
