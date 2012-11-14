""" Scaling groups REST mock API"""

from twisted.web.resource import Resource
from util.schema import validate_body
from util.fault import fails_with, succeeds_with
from klein import resource, route
from twisted.internet import defer
import json
from otter.models.interface import \
    scaling_group_config_schema, NoSuchScalingGroupError

groups = {}
ids = 0

_store = None


def get_store():
    """
    :return: the inventory to be used in forming the REST responses
    :rtype: :class:`cupboard.interface.IInventory` provider
    """
    global _store
    if _store is None:
        from otter.models.mock import MockScalingGroupCollection
        _store = MockScalingGroupCollection()
    return _store


def set_store(i_store_provider):
    """
    Sets the inventory to use in forming the REST responses

    :param i_inventory_provider: the inventory to be used in forming the REST
        responses
    :type i_inventory_provider: :class:`cupboard.interface.IInventory` provider

    :return: None
    """
    global _store
    _store = i_store_provider


#TODO: get these from somewhere
class NoSuchGroup(Exception):
    """Null"""
    pass

exception_codes = {
    'ValidationError': 400,
    'InvalidJsonError': 400,
    'NoSuchEntity': 404,
    'NoSuchEntityType': 404,
    NoSuchScalingGroupError.__name__: 404
}


def _format_groups(stuff):
    res = map(lambda format: {'id': format.uuid,
                              'region': format.region,
                              'name': format.name},
              stuff)
    return res


def _json_callback(result, request):
    """
    General callback handler for responses - sets the response code to 200 (OK)
    and returns the result as a JSON string

    :return: JSON string version of the result
    :rtype: ``string``
    """
    return json.dumps(result)


@route('/<string:tenantid>/scaling_groups/<string:coloid>/<string:id>/servers/'
       '<string:serverid>', methods=['DELETE'])
def deleteScalingGroupServers(request, tenantid, coloid, id, serverid):
    """Get a list of the servers in a scaling group.

    Returns a string and 200

    """
    return "DELETE SERVER"


@route('/<string:tenantid>/scaling_groups/<string:coloid>/<string:id>/servers',
       methods=['GET'])
def getScalingGroupServers(request, tenantid, coloid, id):
    """Get a list of the servers in a scaling group.

    Returns a string and 200

    """
    return "GET SCALING GROUP LIST"


@route('/<string:tenantid>/scaling_groups/<string:coloid>/<string:id>',
       methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def getScalingGroup(request, tenantid, coloid, id):
    """Get config for a scaling group.

    Returns a string

    """
    rec = get_store().get_scaling_group(tenantid, coloid, id)
    deferred = defer.maybeDeferred(rec.view_config)
    deferred.addCallback(_json_callback, request)
    return deferred


@route('/<string:tenantid>/scaling_groups/<string:coloid>/<string:id>',
       methods=['PUT'])
@fails_with(exception_codes)
@succeeds_with(200)
@validate_body(scaling_group_config_schema)
def editScalingGroup(request, tenantid, coloid, id, data):
    """Edit config for a scaling group.

    Returns a string

    """
    rec = get_store().get_scaling_group(tenantid, coloid, id)
    deferred = defer.maybeDeferred(rec.update_config, data)
    return deferred


@route('/<string:tenantid>/scaling_groups/<string:coloid>/<string:id>',
       methods=['DELETE'])
@fails_with(exception_codes)
@succeeds_with(204)
def deleteScalingGroup(request, tenantid, coloid, id):
    """Delete a scaling group.

    Returns a string

    """
    deferred = defer.maybeDeferred(get_store().delete_scaling_group,
                                   tenantid, coloid, id)
    return deferred


@route('/<string:tenantid>/scaling_groups',  methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def getAllScalingGroups(request, tenantid):
    """Get a list of scaling groups.

    Returns a string

    """
    deferred = defer.maybeDeferred(get_store().list_scaling_groups, tenantid)
    deferred.addCallback(_format_groups)
    deferred.addCallback(_json_callback, request)
    return deferred


@route('/<string:tenantid>/scaling_groups/<string:coloid>',  methods=['GET'])
@fails_with(exception_codes)
@succeeds_with(200)
def getScalingGroups(request, tenantid, coloid):
    """Get a list of scaling groups.

    Returns a string

    """
    deferred = defer.maybeDeferred(get_store().list_scaling_groups,
                                   tenantid, coloid)
    deferred.addCallback(_format_groups)
    deferred.addCallback(_json_callback, request)
    return deferred


@route('/<string:tenantid>/scaling_groups/<string:coloid>', methods=['POST'])
@fails_with(exception_codes)
@succeeds_with(201)
@validate_body(scaling_group_config_schema)
def createNewScalingGroup(request, tenantid, coloid, data):
    """Create a new scaling group.

    Returns a string

    """

    def send_redirect(uuid, request):
        request.setHeader("Location",
                          "http://127.0.0.1/scaling_groups/{0}/{1}/".
                          format(coloid, uuid))

    deferred = defer.maybeDeferred(get_store().create_scaling_group, tenantid,
                                   coloid, data)
    deferred.addCallback(send_redirect, request)
    return deferred


root = Resource()
root.putChild('v1.0', resource())
