""" Scaling groups REST mock API"""

from twisted.web.resource import Resource
from twisted.web.error import NoResource
import json

groups = {}
ids = 0


class ScaledServer(Resource):

    """Scaled Server resource."""

    def __init__(self, server):
        Resource.__init__(self)

    def render_DELETE(self, request):
        """Delete request.

        Returns a string

        """
        request.setResponseCode(204)
        return ""


class ScaledServerGroup(Resource):

    """ Resource for a group of scaled servers."""

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
        """Get a list of the servers in a scaling group.

        Returns a string and 200

        """
        return "GET SCALING GROUP LIST"

    def render_POST(self, request):
        """Add a server to a scaling group.

        Returns a string amd 200 with a redirect

        """
        request.setResponseCode(200)
        request.setHeader("Location",
                          "http://127.0.0.1/scaling_groups/servers/blah")
        return "ADDED"

    def getChild(self, server, request):
        """Get an individual server resource.

        Returns a resource

        """
        return ScaledServer(server)


class ScalingGroup(Resource):

    """ Resource for a scaling group."""

    def __init__(self, id):
        self.id = id
        Resource.__init__(self)

    def render_GET(self, request):
        """Get config for a scaling group.

        Returns a string

        """
        global groups
        return json.dumps(groups[self.id])

    def render_PUT(self, request):
        """Edit config for a scaling group.

        Returns a string

        """
        request.setResponseCode(200)
        return "EDITED"

    def render_DELETE(self, request):
        """Delete a scaling group.

        Returns a string

        """
        request.setResponseCode(204)
        return ""

    def getChild(self, sub, request):
        """Get the server lists.

        Returns a resource

        """
        if (sub == "servers"):
            return ScaledServerGroup()
        else:
            return NoResource()


class ScalingGroupList(Resource):

    """ Resource for a list of scaling groups."""

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
        """Get a list of scaling groups.

        Returns a string

        """
        global groups
        return json.dumps(groups)

    def render_POST(self, request):
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

    def getChild(self, id, request):
        """Get the individual groups.

        Returns a resource

        """
        global groups
        if id in groups:
            return ScalingGroup(id)
        else:
            return NoResource()

root = Resource()

root.putChild('scaling_groups', ScalingGroupList())
