"""Contains reusable classes relating to mimic."""

from __future__ import print_function

import json

from characteristic import Attribute, attributes

import treq

from twisted.internet.defer import inlineCallbacks, returnValue

from otter.integration.lib.utils import diagnose

from otter.util.http import check_success


@inlineCallbacks
def _sequenced_behaviors(test_case, pool, endpoint, criteria, behaviors,
                         _treq):
    """
    Cause an endpoint fail sometimes or all the time, with a pre-determined
    sequence of successes and/or failures.

    :param str endpoint: The endpoint for the mimic behavior to POST to
    :param pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :param list criteria: The criteria that the event should apply for the
        behavior to work
    :param list behaviors:  A list of dictionaries containing the names of
        behaviors parameters.
    :param _treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.

    :return: the ID of the created behavior
    :rtype: `str`
    """
    body = yield _treq.post(
        endpoint,
        json.dumps({
            "criteria": criteria,
            "name": "sequence",
            "parameters": {
                "behaviors": behaviors
            }
        }),
        pool=pool
    ).addCallback(check_success, [201]).addCallback(_treq.json_content)

    behavior_id = body['id']

    if test_case is not None:
        test_case.addCleanup(
            _delete_behavior, pool, endpoint, behavior_id, _treq)

    returnValue(behavior_id)


@diagnose("mimic", "Deleting behavior")
def _delete_behavior(pool, endpoint, behavior_id, _treq):
    """
    Given a behavior ID, delete it from mimic.

    :param str endpoint: The endpoint for the mimic behavior to POST to
    :param pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :param str behavior_id: The ID of the behavior to delete.
    :param _treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    d = _treq.delete("{0}/{1}".format(endpoint, behavior_id), pool=pool)
    d.addCallback(check_success, [204, 404])
    d.addCallback(_treq.content)
    return d


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
    @diagnose("mimic", "Changing a server's status")
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
            pool=self.pool
        ).addCallback(check_success, [201]).addCallback(self.treq.content)

    @diagnose("mimic", "Injecting create server behavior")
    def sequenced_behaviors(self, rcs, criteria, behaviors,
                            event_description="creation"):
        """
        Cause Nova to fail sometimes or all the time, with a pre-determined
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
        return _sequenced_behaviors(
            self.test_case, self.pool,
            "{0}/behaviors/{1}".format(rcs.endpoints['mimic_nova'],
                                       event_description),
            criteria, behaviors, self.treq)

    @diagnose("mimic", "Deleting create server behavior")
    def delete_behavior(self, rcs, behavior_id, event_description="creation"):
        """
        Given a behavior ID, delete it from mimic.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param str behavior_id: The ID of the behavior to delete.
        :param event_description: What type of event this is that should be
            deleted.
        """
        return _delete_behavior(
            self.pool, "{0}/behaviors/{1}".format(rcs.endpoints['mimic_nova'],
                                                  event_description),
            behavior_id, self.treq)


@attributes(["pool",
             Attribute("test_case", default_value=None),
             Attribute("treq", default_value=treq)])
class MimicIdentity(object):
    """
    Class that handles HTTP requests to the Mimic Identity control plane.

    Please see the Mimic generic control plane (:mod:`mimic.model.behaviors`)
    and specific auth failure behaviors (:class:`mimic.rest.auth_api`) in the
    mimic codebase for more information.

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :ivar test_case: a :class:`twisted.trial.unittest.TestCase`, which if not
        None, will be used to clean up added behaviors.
    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    @diagnose("mimic", "Injecting auth behavior")
    def sequenced_behaviors(self, identity_endpoint, criteria, behaviors,
                            event_description="auth"):
        """
        Cause Identity to fail sometimes or all the time, with a pre-determined
        sequence of successes and/or failures.

        :param identity_endpoint: The endpoint with which to auth against
            identity - the mimic identity control endpoint is hardcoded, so
            this can tell us what the control endpoint is.
        :param list criteria: The criteria for the servers that should exhibit
            this behavior.  See, in mimic the control plane API,
            :func:`register_creation_behavior`, for more information.
        :param list behaviors:  A list of dictionaries containing the names of
            creation behaviors parameters.
            See, in the mimic codebase,
            :func:`mimic.model.nova_objects.sequence` for more information.
        :param str event_description: Which event this sequence of behaviors
            should apply to - the default event is authentication.

        :return: the ID of the created behavior
        :rtype: `str`
        """
        endpoint = identity_endpoint.replace(
            "/identity/v2.0",
            "/mimic/v1.1/IdentityControlAPI/behaviors/{0}".format(
                event_description))
        return _sequenced_behaviors(self.test_case, self.pool, endpoint,
                                    criteria, behaviors, self.treq)


@attributes(["pool",
             Attribute("test_case", default_value=None),
             Attribute("treq", default_value=treq)])
class MimicCLB(object):
    """
    Class that handles HTTP requests to the mimic Cloud Load Blancer
    control plane.

    Please see the mimic control plane API
    (:class:`mimic.rest.loadbalancer_api.LoadBalancerControlRegion`) in the
    mimic codebase for more information.

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :ivar test_case: a :class:`twisted.trial.unittest.TestCase`, which if not
        None, will be used to clean up added behaviors.
    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    @diagnose("mimic", "Setting CLB status")
    def set_clb_attributes(self, rcs, clb_id, kvpairs):
        """
        Update the attributes of a clould load balancer based on the provided
        key, value pairs.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param clb_id: The ID of the load balancer to be altered
        :param dict kvpairs: A dictionary of key value pairs. The keys
        correspond to attributes in the load balancer details and the value is
        what the attribute will be replaced with.
        See the `mimic.model.RegionalCLBCollection.set_attribue` function
        for the supported attributes.
        :return: A deferred that fires with the content of the response, which
            is probably the empty string.
        """
        print('Use mimic to set CLB attribute')
        return self.treq.patch(
            "{0}/loadbalancer/{1}/attributes".format(
                rcs.endpoints["mimic_clb"], clb_id),
            json.dumps(kvpairs),
            pool=self.pool
        ).addCallback(check_success, [204]).addCallback(self.treq.content)
