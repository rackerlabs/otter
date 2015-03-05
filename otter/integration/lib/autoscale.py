"""Contains reusable classes relating to autoscale."""

from __future__ import print_function

import json

from characteristic import Attribute, attributes

import treq

from twisted.internet import reactor
from twisted.internet.task import LoopingCall

from otter.util.http import check_success, headers


class TimeoutError(Exception):
    """This exception will raise when an operation exceeds a maximum amount
    of time without showing any progress.
    """


@attributes([
    Attribute('group_config', instance_of=dict),
    Attribute('pool', default_value=None),
    Attribute('reactor', default_value=None),
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

    def wait_for_N_servers(
        self, rcs, servers_desired, period=10, timeout=600, clock=None
    ):
        """Waits for the desired number of servers.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.
        :param int servers_desired: The number of servers to wait for.
            It must be greater than or equal to one.
        :param int period: The number of seconds between poll attempts.
            If unspecified, defaults to 10 seconds.
        :param int timeout: The number of seconds to wait before giving up.
            Defaults to 600 seconds (10 minutes).
        :param twisted.internet.interfaces.IReactorTime clock: If provided,
            the clock to use for scheduling things.  Defaults to `reactor`
            if not specified.

        :return: If the operation succeeds, the same instance of TestResources.
            Otherwise, an exception is raised.
        """

        clock = clock or reactor

        class Looper(object):
            """Inner-class to support looping until either of two conditions
            holds: (1) we see at least `servers_desired` servers in existence,
            or (2) a timeout is reached.

            :param ScalingGroup scaling_group: The scaling group that this
                looper should poll the state of.
            """

            def __init__(self, scaling_group):
                self.elapsed_time = 0
                self.scaling_group = scaling_group
                # To be filled in later.
                self.loopingCall = None

            def loop(self):
                if self.elapsed_time < timeout:
                    self.elapsed_time += period
                    return self.check_servers()
                else:
                    raise TimeoutError(
                        "Spent %ds, polling every %ds, timeout." % (
                            self.elapsed_time, period
                        )
                    )

            def ensure_200_result(self, state_results):
                if state_results[0] != 200:
                    raise Exception("Scaling group not found.")
                active_servers = state_results[1]["group"]["active"]
                if len(active_servers) >= servers_desired:
                    self.loopingCall.stop()

            def check_servers(self):
                d = self.scaling_group.get_scaling_group_state(rcs)\
                    .addCallback(self.ensure_200_result)
                return d

        looper = Looper(self)
        lc = LoopingCall(looper.loop)
        lc.clock = clock
        looper.loopingCall = lc
        d = lc.start(period).addCallback(lambda _: rcs)
        return d

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
