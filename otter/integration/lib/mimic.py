"""Contains reusable classes relating to mimic."""

from __future__ import print_function

import json

from characteristic import Attribute, attributes

import treq

from twisted.internet.defer import inlineCallbacks, returnValue

from zope.interface import Attribute as ZopeAttribute
from zope.interface import Interface, implementedBy, implementer

from otter.util.http import check_success


@inlineCallbacks
def _mimic_behaviors(pool, endpoint, behavior_name, criteria, parameters,
                     test_case=None, _treq=treq):
    """
    Generic behavior registration in mimic.  Behavior CRUD is handled
    generically in mimic (:see: :func:`mimic.model.behaviors.make_behavior_api`
    in the Mimic codebase for more information.)

    :see: :mod:`mimic.model.behaviors` in the mimic code base for more
        information on how behaviors work overall.

    Note that mimic does not do authentication, so an auth token is not
    necessary.

    :param str endpoint: The URL for the behavior endpoint (this includes the
        behavior event type - e.g. for nova server creation behaviors, for
        instance, the endpoint would be <nova_control_url>/behaviors/creation).
    :param str behavior_name: The name of the behavior to einject.
    :param list criteria: The criteria for the servers that should exhibit
        this behavior.
    :param dict parameters:  The parameters to pass to the behavior.  What
        form the dictionary should take is dependent upon the behavior
        specified.
    :param test_case: an instance of :class:`twisted.trial.unittest.TestCase`
    :param _treq: The treq instance to use

    :return: the ID of the created behavior
    :rtype: `str`
    """
    body = yield _treq.post(
        endpoint,
        json.dumps({
            "criteria": criteria,
            "name": behavior_name,
            "parameters": parameters
        }),
        pool=pool
    ).addCallback(check_success, [201]).addCallback(_treq.json_content)

    behavior_id = body['id']

    if test_case is not None:
        test_case.addCleanup(
            _mimic_delete_behavior, pool, endpoint, behavior_id,
            test_case, _treq)

    returnValue(behavior_id)


def _mimic_delete_behavior(pool, endpoint, behavior_id, test_case, _treq=treq):
    """
    Generic behavior deletion in mimic.  Behavior CRUD is handled
    generically in mimic (:see: :func:`mimic.model.behaviors.make_behavior_api`
    in the Mimic codebase for more information.)

    Note that mimic does not do authentication, so an auth token is not
    necessary.

    :param str endpoint: The URL for the behavior endpoint (this includes the
        behavior event type - e.g. for nova server creation behaviors, for
        instance, the endpoint would be <nova_control_url>/behaviors/creation).
    :param str behavior_id: The ID of the behavior to delete.
    :param test_case: an instance of :class:`twisted.trial.unittest.TestCase`
    :param _treq: The treq instance to use

    :return: The string body of the response (the empty string)
    :rtype: `str`
    """
    d = _treq.delete("{0}/{1}".format(endpoint, behavior_id), pool=pool)
    d.addCallback(check_success, [204, 404])
    d.addCallback(_treq.content)
    return d


class IMimicBehaviorAPISupporter(Interface):
    """
    Class to be implemented if support for injecting behavior into the mimic
    object is required.
    """
    pool = ZopeAttribute("The HTTP connection pool to be used.")
    test_case = ZopeAttribute("The test case to be used to clean up.")
    treq = ZopeAttribute("The treq module to be used to make requests.")

    def get_behavior_endpoint(rcs, event_description=None):
        """
        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param str event_description: Which event this sequence of behaviors
            should apply to.  Should have a default value.

        :return: the behavior endpoint to be hit
        """


def supports_mimic_behavior_injection(klass):
    """
    Class decorator that adds functions to support registering sequence
    behavior and deleting behavior from a Mimic controller API object.

    :param klass: a :class:`IMimicBehaviorAPISupporter` implementer
    """
    assert IMimicBehaviorAPISupporter in implementedBy(klass)

    def sequenced_behaviors(klass_self, rcs, criteria, behaviors,
                            event_description=None):
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
        return _mimic_behaviors(
            klass_self.pool,
            klass_self.get_behavior_endpoint(rcs, event_description),
            "sequence",
            criteria,
            parameters={"behaviors": behaviors},
            test_case=klass_self.test_case, _treq=klass_self.treq)

    def delete_behavior(klass_self, rcs, behavior_id, event_description=None):
        """
        Given a behavior ID, delete it from mimic.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param event_description: What type of event this is that should be
            deleted.
        :param str behavior_id: The ID of the behavior to delete.
        """
        return _mimic_delete_behavior(
            klass_self.pool,
            klass_self.get_behavior_endpoint(rcs, event_description),
            behavior_id,
            test_case=klass_self.test_case,
            _treq=klass_self.treq)

    setattr(klass, 'sequenced_behaviors', sequenced_behaviors)
    setattr(klass, 'delete_behavior', delete_behavior)
    return klass


@supports_mimic_behavior_injection
@implementer(IMimicBehaviorAPISupporter)
@attributes(["pool",
             Attribute("test_case", default_value=None),
             Attribute("treq", default_value=treq)])
class MimicNova(object):
    """
    Class that handles HTTP requests to the mimic nova control plane.

    Please see the mimic control plane API
    (:class:`mimic.rest.nova_api.NovaControlAPIRegion`) in the mimic
    codebase for more information.

    This also supports behavior injection, with the default type of behavior
    to inject being server creation.

    :see: :func:`supports_mimic_behavior_injection` above

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :ivar test_case: a :class:`twisted.trial.unittest.TestCase`, which if not
        None, will be used to clean up added behaviors.
    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    def get_behavior_endpoint(self, rcs, event_description="creation"):
        """
        Return the default behavior injection endpoint, the default behavior
        being server creation.
        """
        return "{0}/behaviors/{1}".format(rcs.endpoints['mimic_nova'],
                                          event_description)

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


@supports_mimic_behavior_injection
@implementer(IMimicBehaviorAPISupporter)
@attributes(["pool",
             Attribute("test_case", default_value=None),
             Attribute("treq", default_value=treq)])
class MimicIdentity(object):
    """
    Class that handles HTTP requests to the mimic identity control plane.

    Please see the mimic control plane API
    (:func:`mimic.rest.resource.MimicRoot.handle_identity_behaviors`) in the
    mimic codebase for more information.

    This also supports behavior injection, with the default type of behavior
    to inject being authentication.

    :see: :func:`supports_mimic_behavior_injection` above

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests
    :ivar test_case: a :class:`twisted.trial.unittest.TestCase`, which if not
        None, will be used to clean up added behaviors.
    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """
    def get_behavior_endpoint(self, rcs, event_description="creation"):
        """
        Return the default behavior injection endpoint, the default behavior
        being authentication.
        """
        return "/mimic/v1.1/behaviors/{0}".format(event_description)


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
