"""Contains reusable classes relating to mimic."""

from __future__ import print_function

import json

from characteristic import Attribute, attributes

import treq

from twisted.internet.defer import inlineCallbacks, returnValue

from otter.util.http import check_success, headers


@attributes(["pool",
             Attribute("test_case", default_value=None),
             Attribute("treq", default_value=treq)])
class MimicNova(object):
    """
    Class that handles HTTP requests to the mimic nova control plane.

    Please see the mimic control plane API
    (:class:`mimic.rest.nova_api.NovaControlAPIRegion`) in the mimic
    codebase for more information.

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :ivar test_case: a :class:`twisted.trial.unittest.TestCase`, which if not
        None, will be used to clean up added behaviors.
    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    def change_server_statuses(self, rcs, ids_to_status):
        """
        Change the statuses of the given server IDs.  Changing the statuses of
        servers does not require any cleanup, because this is not creating a
        persistent behavior in mimic.

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

    @inlineCallbacks
    def sequenced_behaviors(self, rcs, criteria, behaviors,
                            event_description="creation"):
        """
        Cause nova to fail sometimes or all the time, with a pre-determined
        sequence of successes and/or failures.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param list criteria: The criteria for the servers that should exhibit
            this behavior.  See, in mimic the control plane API,
            :func:`register_creation_behavior`, for more information.
        :param list behaviors:  A list of dictionaries containing the names of
            creation behaviors parameters.
            See, in the mimic codebase,
            :func:`mimic.model.nova_objects.sequence` for more information.
        :param str event_description: Which event this sequence of behaviors
            should apply to - the default event is server creation.

        :return: the ID of the created behavior
        :rtype: `str`
        """
        body = yield self.treq.post(
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
        ).addCallback(check_success, [201]).addCallback(self.treq.json_content)

        behavior_id = body['id']

        if self.test_case is not None:
            self.test_case.addCleanup(
                self.delete_behavior, rcs, behavior_id, event_description)

        returnValue(behavior_id)

    def delete_behavior(self, rcs, behavior_id, event_description="creation"):
        """
        Given a behavior ID, delete it from mimic.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param event_description: What type of event this is that should be
            deleted.
        :param str behavior_id: The ID of the behavior to delete.
        """
        d = self.treq.delete(
            "{0}/behaviors/{1}/{2}".format(rcs.endpoints['mimic_nova'],
                                           event_description, behavior_id),
            headers=headers(str(rcs.token)),
            pool=self.pool
        )
        d.addCallback(check_success, [204, 404])
        d.addCallback(self.treq.content)
        return d
