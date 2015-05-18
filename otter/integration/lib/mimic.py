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

    Please see the mimic control plane API
    (:class:`mimic.rest.nova_api.NovaControlAPIRegion`) in the mimic
    codebase for more information.
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

    def sequenced_behaviors(self, rcs, criteria, behaviors,
                            event_description="creation"):
        """
        Cause nova to fail sometimes or all the time, with a pre-determined
        sequence of successes and/or failures.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param criteria: The criteria for the servers that should exhibit
            this behavior.  See, in mimic the control plane API,
            :func:`register_creation_behavior`, for more information.
        :param behaviors:  A list of dictionaries containing the names of
            creation behaviors parameters.
            See, in the mimic codebase,
            :func:`mimic.model.nova_objects.sequence` for more information.
        :param event_description: Which event this sequence of behaviors
            should apply to - the default event is server creation.
        """
        return self.treq.post(
            "{0}/behaviors/{1}".format(rcs.endpoints['mimic_nova'],
                                       event_description),
            json.dumps({
                "criteria": criteria,
                "name": "sequence",
                "parameters": {
                    "behaviors": behaviors
                }
            }),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, [201]).addCallback(self.treq.content)
