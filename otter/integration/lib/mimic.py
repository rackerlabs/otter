"""Contains reusable classes relating to mimic."""

from __future__ import print_function

import json

from characteristic import Attribute, attributes

import treq

from otter.util.http import check_success, headers


@attributes(["pool", Attribute("treq", default_value=treq)])
class MimicNova(object):
    """
    Class that handles HTTP requests to the mimic nova control plane.
    """
    def change_server_statuses(self, rcs, ids_to_status):
        """
        Change the statuses of the given server IDs.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param dict ids_to_status: A mapping of server IDs to the string status
            to which they should be changed.  (see
            http://docs.rackspace.com/servers/api/v2/cs-devguide/content/
            List_Servers_Server_Statuses-d1e2078.html for a list of statuses)

        :return: A deferred that fires with the content of the response, which
            is probably the empty string.
        """
        return self.treq.post(
            "{0}/attributes".format(rcs.endpoints["mimic_nova"]),
            json.dumps({"status": ids_to_status}),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, [201]).addCallback(self.treq.content)
