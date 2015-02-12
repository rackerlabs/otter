"""The lib module provides a library of classes and functions useful for
writing integration tests in the context of the Otter project.
"""

import json

from characteristic import Attribute, attributes

from pyrsistent import freeze

import treq

from otter.util.http import check_success, headers


@attributes([
    Attribute('access', default_value=None),
    Attribute('other', default_value=None),
    Attribute('endpoints', default_value={}),
    Attribute('groups', default_value=[]),
])
class TestResources(object):
    """This class records the various resources used by a test.
    It is NOT intended to be used for clean-up purposes (use
    :func:`unittest.addCleanup` for this purpose).  Instead, it's just a
    useful scratchpad for passing test resource availability amongst Twisted
    callbacks.

    If you have custom state you'd like to pass around, use the :attr:`other`
    attribute for this purpose.  The library will not interpret this attribute,
    nor will it change it (bugs notwithstanding).
    """


@attributes([
    Attribute('auth'),
    Attribute('username', instance_of=str),
    Attribute('password', instance_of=str),
    Attribute('endpoint', instance_of=str),
    Attribute('pool', default_value=None),
])
class IdentityV2(object):
    """This class provides a way to configure commonly used parameters
    exactly once for any number of Identity-related API calls.

    :param module auth: Either the ``otter.auth`` module, or a compatible
        interface for testing purposes.
    :param str username: The username you wish to authenticate against
        Identity with.
    :param str password: The password you wish to authenticate against
        Identity with.
    :param str endpoint: The Identity V2 API base endpoint address.
    :param twisted.web.client.HTTPConnectionPool pool: If left
        unspecified, Twisted will use its own connection pool for making
        HTTP requests.  When running tests via Trial, this may cause
        some race conditions inside the treq module.  Providing your
        own connection pool for manual management inside of a test class'
        setUp and tearDown methods will work around this problem.
        See https://github.com/dreid/treq/blob/master/treq/
        test/test_treq_integration.py#L60-L74 for more information.
    """

    def __init__(self):
        self.access = None

    def authenticate_user(self, rcs):
        """Authenticates against the Identity API.  Prior to success, the
        :attr:`access` member will be set to `None`.  After authentication
        completes, :attr:`access` will hold the raw Identity V2 API results as
        a Python dictionary, including service catalog and API authentication
        token.

        :param TestResources rcs: A :class:`TestResources` instance used to
            record the identity results.

        :return: A Deferred which, when fired, returns a copy of the resources
            given.  The :attr:`access` field will be set to the Python
            dictionary representation of the Identity authentication results.
        """

        def record_result(r):
            rcs.access = freeze(r)
            return rcs

        return self.auth.authenticate_user(
            self.endpoint, self.username, self.password, pool=self.pool
        ).addCallback(record_result)


@attributes([
    Attribute('group_config', instance_of=dict),
    Attribute('pool', default_value=None),
])
class ScalingGroup(object):
    """This class encapsulates a scaling group resource.  It provides a means
    which lets you create new scaling groups and, later, automatically
    dispose of them upon integration test completion.
    """

    def stop(self, rcs):
        """Clean up a scaling group.  Although safe to call yourself, you
        should think twice about it.  Let :method:`start` handle registering
        this function for you.

        At the present time, this function DOES NOT stop to verify
        servers are removed.  (This is because I haven't created
        any tests which create them yet.)
        """

        return self.delete_scaling_group(rcs)

    def delete_scaling_group(self, rcs):
        """Unconditionally delete the scaling group.  You may call this only
        once.

        :return: A :class:`Deferred` which, upon firing, disposes of the
            scaling group.
        """

        return (treq.delete(
            "%s/groups/%s?force=true" % (
                str(rcs.endpoints["otter"]), self.group_id
            ),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, [204, 404]))

    def get_scaling_group_state(self, rcs):
        """Retrieve the state of the scaling group.

        :return: A :class:`Deferred` which, upon firing, returns the result
            code and, optionally, scaling group state as a 2-tuple, in that
            order.  If not found, the result code will be 404, and the state
            will be None.
        """

        def decide(resp):
            if resp.code == 200:
                return treq.json_content(resp).addCallback(lambda x: (200, x))
            return (404, None)

        return (
            treq.get(
                "%s/groups/%s/state" % (
                    str(rcs.endpoints["otter"]), self.group_id
                ),
                headers=headers(str(rcs.token)),
                pool=self.pool
            ).addCallback(check_success, [200, 404])
            .addCallback(decide)
        )

    def start(self, rcs, test):
        """Create a scaling group.

        :param TestResources rcs: A set of OpenStack resources encapsulated
            in a TestResources instance.

        :return: The same instance of TestResources.
        """

        test.addCleanup(self.stop, rcs)

        def record_results(resp):
            rcs.groups.append(resp)
            self.group_id = str(resp["group"]["id"])
            return rcs

        return (
            treq.post(
                "%s/groups" % str(rcs.endpoints["otter"]),
                json.dumps(self.group_config),
                headers=headers(str(rcs.token)),
                pool=self.pool
            )
            .addCallback(check_success, [201])
            .addCallback(treq.json_content)
            .addCallback(record_results)
        )


@attributes([
    Attribute('scale_by', instance_of=int),
    Attribute('scaling_group', instance_of=ScalingGroup),
])
class ScalingPolicy(object):
    """ScalingPolicy class instances represent individual policies which your
    integration tests can execute at their convenience.

    :param int scale_by: The number of servers to scale up (positive) or down
        (negative) by.  Cannot be zero, lest an API-generated error occur.
    :param ScalingGroup scaling_group: The scaling group to which this policy
        applies.
    """

    def __init__(self):
        self.policy = [{
            "name": "integration-test-policy",
            "cooldown": 0,
            "type": "webhook",
            "change": self.scale_by
        }]

    def stop(self, rcs):
        """Disposes of the policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, when triggered, removes the scaling
            policy.  It returns the test resources supplied, easing continuity
            of integration test code.
        """
        return self.delete(rcs)

    def start(self, rcs, test):
        """Creates and registers, but does not execute, the policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :param twisted.trial.unittest.TestCase test: The test case running the
            integration test.

        :return: A :class:`Deferred` which, when triggered, creates the scaling
            policy and registers it with AutoScale API.  It does not execute
            the policy, however.  The policy, when created, will also appear in
            the test resources `groups` list.  The full JSON will be available
            for inspection.  In addition, this object's :attribute:`policy_id`
            member will contain the ID of the policy.

            The deferred will itself return the TestResources instance
            provided.
        """
        test.addCleanup(self.stop, rcs)

        def record_results(resp):
            self.policy_id = resp["policies"][0]["id"]
            self.link = str(resp["policies"][0]["links"][0]["href"])
            return rcs

        return (
            treq.post(
                "%s/groups/%s/policies" % (
                    str(rcs.endpoints["otter"]), self.scaling_group.group_id
                ),
                json.dumps(self.policy),
                headers=headers(str(rcs.token)),
                pool=self.scaling_group.pool,
            )
            .addCallback(check_success, [201])
            .addCallback(treq.json_content)
            .addCallback(record_results)
        )

    def delete(self, rcs):
        """Removes the scaling policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, when triggered, removes the scaling
            policy.  It returns the test resources supplied, easing continuity
            of integration test code.
        """
        return (
            treq.delete(
                "%s?force=true" % self.link,
                headers=headers(str(rcs.token)),
                pool=self.scaling_group.pool,
            )
            .addCallback(check_success, [204, 404])
        ).addCallback(lambda _: rcs)

    def execute(self, rcs):
        """Executes the scaling policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, when triggered, removes the scaling
            policy.  It returns the test resources supplied, easing continuity
            of integration test code.
        """
        return (
            treq.post(
                "%sexecute" % self.link,
                headers=headers(str(rcs.token)),
                pool=self.scaling_group.pool,
            ).addCallback(check_success, [202])
            # Policy execution does not return anything meaningful,
            # per http://tinyurl.com/ndds6ap (link to docs.rackspace).
            # So, we forcefully return our resources here.
            .addCallback(lambda _, x: x, rcs)
        )
        return rcs


def find_endpoint(catalog, service_type, region):
    """Locate an endpoint in a service catalog, as returned by IdentityV2.
    Please note that both :param:`service_type` and :param:`region` are
    case sensitive.

    :param dict catalog: The Identity service catalog.
    :param str service_type: The type of service to look for.
    :param str region: The service region the desired endpoint must service.
    :return: The endpoint offering the desired type of service for the
        desired region, if available.  None otherwise.
    """
    for entry in catalog["access"]["serviceCatalog"]:
        if entry["type"] != service_type:
            continue
        for endpoint in entry["endpoints"]:
            if endpoint["region"] == region:
                return endpoint["publicURL"]
    return None
