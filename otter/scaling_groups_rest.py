""" Scaling groups REST mock API"""

from twisted.web.resource import Resource
from klein import resource, route
import json

groups = {}
ids = 0


@route('/<string:tenantid>/scaling_groups/<string:id>/servers/<string:serverid>',  methods=['DELETE'])
def deleteScalingGroupServers(request, tenantid, id, serverid):
    """Get a list of the servers in a scaling group.

    Returns a string and 200

    """
    return "DELETE SERVER"


@route('/<string:tenantid>/scaling_groups/<string:id>/servers',  methods=['GET'])
def getScalingGroupServers(request, tenantid, id):
    """Get a list of the servers in a scaling group.

    Returns a string and 200

    """
    return "GET SCALING GROUP LIST"

@route('/<string:tenantid>/scaling_groups/<string:id>/servers',  methods=['POST'])
def addScalingGroupServer(request, tenantid, id):
    """Add a server to a scaling group.

    Returns a string amd 200 with a redirect

    """
    request.setResponseCode(200)
    request.setHeader("Location",
                      "http://127.0.0.1/scaling_groups/servers/blah")
    return "ADDED"

@route('/<string:tenantid>/scaling_groups/<string:id>',  methods=['GET'])
def getScalingGroup(request, tenantid, id):
    """Get config for a scaling group.

    Returns a string

    """
    global groups
    return json.dumps(groups[id])

@route('/<string:tenantid>/scaling_groups/<string:id>',  methods=['PUT'])
def editScalingGroup(request, tenantid, id):
    """Edit config for a scaling group.

    Returns a string

    """
    request.setResponseCode(200)
    return "EDITED"

@route('/<string:tenantid>/scaling_groups/<string:id>',  methods=['DELETE'])
def deleteScalingGroup(request, tenantid, id):
    """Delete a scaling group.

    Returns a string

    """
    request.setResponseCode(204)
    return ""

@route('/<string:tenantid>/scaling_groups',  methods=['GET'])
def getScalingGroups(request, tenantid):
    """Get a list of scaling groups.

    Returns a string

    """
    global groups
    return json.dumps(groups)


@route('/<string:tenantid>/scaling_groups',  methods=['POST'])
def createNewScalingGroup(request, tenantid):
    """Create a new scaling group.

    Returns a string

    """
    rData = json.load(request.content)
    for key in [('name', basestring),
                ('regions', list), ('cooldown', int),
                ('min_servers', int), ('max_servers', int),
                ('desired_servers', int), ('image', basestring)]:
        if not key[0] in rData:
            request.setResponseCode(400)
            return "{0} is required".format(key[0])
        if not isinstance(rData[key[0]], key[1]):
            request.setResponseCode(400)
            return "{0} is wrong type".format(key[0])
    # Do creation here
    global ids
    idstr = "gr{0}".format(ids)
    ids = ids + 1
    groups[idstr] = rData
    request.setResponseCode(201)
    request.setHeader("Location",
                      "http://127.0.0.1/scaling_groups/{0}/".format(idstr))
    return "CREATED"

root = Resource()
root.putChild('v1.0', resource())
