"""Contains reusable classes relating to autoscale."""

from __future__ import print_function

import datetime
import json
import os

from characteristic import Attribute, attributes

import treq

from twisted.internet import reactor

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    transient_errors_except,
)


class BreakLoopException(Exception):
    """This serves to break out of a `retry_and_timeout` loop."""


def extract_active_ids(group_status):
    """Extracts all server IDs from a scaling group's status report.

    :param dict group_status: The successful result from
        ``get_scaling_group_state``.
    :result: A list of server IDs known to the scaling group.
    """
    return [obj['id'] for obj in group_status['group']['active']]


def create_scaling_group_dict(
    image_ref=None, flavor_ref=None, min_entities=0, name=None,
    max_entities=25, use_lbs=None
):
    """This function returns a dictionary containing a scaling group's JSON
    payload.  Note: this function does NOT create a scaling group.

    :param str image_ref: An OpenStack image reference ID (typically a UUID).
        If not provided, the content of the AS_IMAGE_REF environment variable
        will be taken as default.  If that doesn't exist, "" will be used.
    :param str flavor_ref: As with image_ref above, but for the launch config's
        flavor setting.
    :param int min_entities: The minimum number of servers to bring up when
        the scaling group is eventually created or operating.  If not
        specified, 0 is assumed.
    :param int max_entities: The maximum number of servers to allow in the
        scaling group. If not specified, 25 is the default.
    :param str name: The scaling group name.  If not provided, a default is
        chosen.
    :param list use_lbs: Specifies a list of one or more cloud or RackConnect
        load balancer JSON *dictionary* objects.  These are *not* instances of
        ``otter.lib.CloudLoadBalancer``.  However, you can get the dicts by
        invoking the o.l.CLB.scaling_group_spec() method on such objects.  If
        not given, no load balancers will be used.
    :return: A dictionary containing a scaling group JSON descriptor.  Inside,
        it will contain a default launch config with the provided (or assumed)
        flavor and image IDs.
    """

    if not image_ref:
        image_ref = os.environ['AS_IMAGE_REF']
    if not flavor_ref:
        flavor_ref = os.environ['AS_FLAVOR_REF']
    if not name:
        name = "automatically-generated-test-configuration"

    obj = {
        "launchConfiguration": {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": flavor_ref,
                    "imageRef": image_ref,
                }
            }
        },
        "groupConfiguration": {
            "name": name,
            "cooldown": 0,
            "minEntities": min_entities,
            "maxEntities": max_entities,
        },
        "scalingPolicies": [],
    }

    if use_lbs:
        obj["launchConfiguration"]["args"]["loadBalancers"] = use_lbs

    return obj


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

    def set_launch_config(self, rcs, launch_config):
        """Changes the launch configuration used by the scaling group.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :param dict launch_config: The new launch configuration.

        :return: A :class:`Deferred` which, upon firing, alters the scaling
            group's launch configuration.  If successful, the test resources
            provided will be returned.  Otherwise, an exception will rise.
        """
        return (
            treq.put(
                "%s/groups/%s/launch" % (
                    str(rcs.endpoints["otter"]), self.group_id
                ),
                json.dumps(launch_config),
                headers=headers(str(rcs.token)),
                pool=self.pool
            ).addCallback(check_success, [204])
            .addCallback(lambda _: rcs)
        )

    def stop(self, rcs):
        """Clean up a scaling group.  Although safe to call yourself, you
        should think twice about it.  Let :method:`start` handle registering
        this function for you.

        At the present time, this function DOES NOT stop to verify
        servers are removed.  (This is because I haven't created
        any tests which create them yet.)

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.
        """

        return self.delete_scaling_group(rcs)

    def delete_scaling_group(self, rcs):
        """Unconditionally delete the scaling group.  You may call this only
        once.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

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

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, upon firing, returns the result
            code and, optionally, scaling group state as a 2-tuple, in that
            order.  If not found, the result code will be 404, and the state
            will be None.
        """

        def decide(resp):
            if resp.code == 200:
                return treq.json_content(resp).addCallback(lambda x: (200, x))
            return (404, None)
        # ids = map(lambda obj: obj['id'], response['group']['active'])

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

        def check((code, response)):
            if code == 404:
                raise BreakLoopException("Scaling group not found.")
            servers_active = len(response["group"]["active"])
            if servers_active == servers_desired:
                return rcs

            raise TransientRetryError()

        def poll():
            return self.get_scaling_group_state(rcs).addCallback(check)

        return retry_and_timeout(
            poll, timeout,
            can_retry=transient_errors_except(BreakLoopException),
            next_interval=repeating_interval(period),
            clock=clock or reactor,
            deferred_description=(
                "Waiting for {} servers to go active.".format(
                    servers_desired
                )
            )
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

    def wait_for_deleted_id_removal(
        self, removed_ids, rcs, timeout=60, period=1, total_servers=None
    ):
        """Wait for the scaling group to reflect the true state of the tenant's
        server states.  Out-of-band server deletions or servers which
        transition to an ERROR state should eventually be removed from the
        scaling group's list of active servers.

        :param list removed_ids: A list of server IDs that we should expect
            the scaling group to realize are gone eventually.
        :param TestResources rcs: The test resources necessary to invoke API
            calls and manage state.
        :param int timeout: The number of seconds to wait before giving up.
        :param int period: The number of seconds between each check for ID
            removal.
        :param int total_servers: If provided, the total number of servers in
            your scaling group.  This parameter is used for error reporting
            purposes only.
        :return: It'll return the value of ``rcs`` if successful.  An exception
            will be raised otherwise, including timeout.
        """

        def check((code, response)):
            if code == 404:
                raise BreakLoopException(
                    "Scaling group appears to have disappeared"
                )

            active_ids = extract_active_ids(response)
            print("wait_for_deleted_id_removal: {0}".format(active_ids))
            for deleted_id in removed_ids:
                if deleted_id in active_ids:
                    raise TransientRetryError()

            return rcs

        def poll():
            return self.get_scaling_group_state(rcs).addCallback(check)

        if total_servers:
            report = (
                "Scaling group failed to reflect {} of {} servers removed."
                .format(len(removed_ids), total_servers)
            )
        else:
            report = (
                "Scaling group failed to reflect {} servers removed."
                .format(len(removed_ids))
            )

        return retry_and_timeout(
            poll, timeout,
            can_retry=transient_errors_except(BreakLoopException),
            next_interval=repeating_interval(period),
            clock=reactor,
            deferred_description=report,
        )

    def wait_for_expected_state(self, _, rcs, timeout=60, period=1,
                                active=None, pending=None, desired=None):
        """
        Repeatedly get the group state until either the specified timeout has
        occurred or the specified number of active, pending, and desired
        servers is observed. Unspecifed quantities default to None and are
        treated as don't cares.
        """

        def check((code, response)):
            if code != 200:
                raise BreakLoopException(
                    "Could not get the scaling group state"
                )

            n_active = len(response["group"]["active"])
            n_pending = response["group"]["pendingCapacity"]
            n_desired = response["group"]["desiredCapacity"]
            print("Active: {0}, Pending: {1}, Desired: {2}".format(n_active,
                                                                   n_pending,
                                                                   n_desired))

            # print(response["group"])
            if ((active is None or active == n_active)
                    and
                    (pending is None or pending == n_pending)
                    and
                    (desired is None or desired == n_desired)):
                return rcs

            raise TransientRetryError()

        def poll():
            return self.get_scaling_group_state(rcs).addCallback(check)

        return retry_and_timeout(
            poll, timeout,
            can_retry=transient_errors_except(BreakLoopException),
            next_interval=repeating_interval(period),
            clock=reactor,
            deferred_description=(
                "Waiting for Autoscale to see expected state of"
                "(active, pending, desired) "
                "= ({0}, {1}, {2}".format(active, pending, desired)
            )
        )


@attributes([
    Attribute('scale_by', default_value=None),
    Attribute('scaling_group', instance_of=ScalingGroup),
    Attribute('set_to', default_value=None),
    Attribute('scale_percent', default_value=None),
    Attribute('name', instance_of=str, default_value='integration-test-policy')
])
class ScalingPolicy(object):
    """ScalingPolicy class instances represent individual policies which your
    integration tests can execute at their convenience. Only one of (scale_by,
    set_to, scale_percent) should be provided. If more than one is provided,
    this function will blindly include them in the policy creation request.

    :param int scale_by: The number of servers to scale up (positive) or down
        (negative) by.  Cannot be zero, lest an API-generated error occur.
    :param ScalingGroup scaling_group: The scaling group to which this policy
        applies.
    :param int set_to: The number of servers to set as the desired capacity
    :param float scale_percent: The percentage by which to scale the group up
        (positive) or down (negative)
    :param str name: A string to use as the name of the scaling policy. A
        timestamp will be appended automatically for differentiation.
    """

    def __init__(self):

        name_time = '{0}_{1}'.format(self.name,
                                     datetime.datetime.utcnow().isoformat())
        change_type = ""
        change_factor = 0
        if self.scale_by:
            change_type = "change"
            change_factor = self.scale_by
        elif self.set_to:
            change_type = "desiredCapacity"
            change_factor = self.set_to
        elif self.scale_percent:
            change_type = "changePercent"
            change_factor = self.scale_percent

        self.policy = [{
            "name": name_time,
            "cooldown": 0,
            "type": "webhook",
            change_type: change_factor
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
