"""Contains reusable classes relating to autoscale."""

from __future__ import print_function

import datetime
import json
import os
import pprint
import random

from characteristic import Attribute, attributes

from testtools.matchers import MatchesPredicateWithParams

import treq

from twisted.internet import reactor
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.python.log import msg

from otter.integration.lib.nova import NovaServer
from otter.integration.lib.utils import diagnose

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    terminal_errors_except
)

pp = pprint.PrettyPrinter(indent=4)
verbosity = int(os.environ.get('AS_VERBOSITY', 0))

if verbosity > 0:
    print('Verbosity level ... {0}'.format(verbosity))


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
    max_entities=25, use_lbs=None, server_name_prefix=None,
    key_name=None, draining_timeout=None
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
    :param str server_name_prefix: Specifies a server name in the server
        args that get passed to autoscale - autoscale will use this as the
        prefix of all server names created by the group.
    :param str key_name: Specifies an ssh key name in the server
        args that get passed to autoscale - autoscale will use this as the
        prefix of all server names created by the group.

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
                    "networks": [
                        {
                            "uuid": "11111111-1111-1111-1111-111111111111"
                        }
                    ]
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

    launch_config_args = obj["launchConfiguration"]["args"]
    if use_lbs:
        launch_config_args["loadBalancers"] = use_lbs

    if server_name_prefix is not None:
        launch_config_args["server"]["name"] = server_name_prefix

    if key_name is not None:
        launch_config_args["server"]["key_name"] = key_name

    if draining_timeout is not None:
        launch_config_args["draining_timeout"] = draining_timeout

    return obj


@attributes([
    Attribute('group_config', instance_of=dict),
    Attribute('pool', default_value=None),
    Attribute('reactor', default_value=None),
    Attribute('treq', default_value=treq),
    Attribute('server_client', default_value=NovaServer)
])
class ScalingGroup(object):
    """This class encapsulates a scaling group resource.  It provides a means
    which lets you create new scaling groups and, later, automatically
    dispose of them upon integration test completion.

    :ivar group_config: The complete JSON dictionary the group was
        created with - a dictionary including 'groupConfiguration',
        'launchConfiguration', and maybe 'scalingPolicies'

    :ivar pool: a :class:`twisted.web.client.HTTPConnectionPool` to pass to
        all treq requests

    :ivar reactor: a :class:`twisted.internet.interfaces.IReactorTime`
        provider, to be used for timeouts and retries

    :ivar treq: the treq module to use for making requests - if not provided,
        the default library :mod:`treq` will be used.  Mainly to be used for
        injecting stubs during tests.
    """

    def _endpoint(self, rcs):
        return "{}/groups/{}".format(
            str(rcs.endpoints["otter"]), self.group_id)

    @diagnose("AS", "Changing launch config")
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
                "{0}/groups/{1}/launch".format(rcs.endpoints["otter"],
                                               self.group_id),
                json.dumps(launch_config),
                headers=headers(str(rcs.token)),
                pool=self.pool
            ).addCallback(check_success, [204])
            .addCallback(lambda _: rcs)
        )

    def get_group_config(self, rcs):
        """
        Returns the group configuration recorded in the TestResources object.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return:
        """
        # Retrieve the configuration from the stored response to group
        # creation since that will include non-provided values
        config = [g['group']['groupConfiguration'] for g in rcs.groups
                  if g['group']['id'] == self.group_id]
        # Since this should always provide a match for a valid scaling group,
        # allow the exception to be raised if nothing is found.
        if verbosity > 0:
            print('ScalingGroup.get_group_config will return: ')
            pp.pprint(config[0])
        return config[0]

    @diagnose("AS", "Changing group config")
    def replace_group_config(self, rcs, replacement_config):
        """
        Replace the current group configuration with the provided config
        and update the stored groupConfiguration information.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.
        :param dict replacement_config: A dictionary representation of
            the JSON description of a scaling group groupConfiguration
            Note that since this is a replacement config, all fields
            in the JSON descirptor are mandatory.

        """

        def record_results(_, replacement_config):
            # Replace the stored value in the group_config
            self.group_config["groupConfiguration"] = replacement_config
            # Find the correct group from the list (by id)
            for g in rcs.groups:
                if g['group']['id'] == self.group_id:
                    g['group']['groupConfiguration'] = replacement_config
            if verbosity > 0:
                print('Update group_config with {}'.format(replacement_config))
            return rcs

        return (
            treq.put(
                "{0}/groups/{1}/config".format(rcs.endpoints["otter"],
                                               self.group_id),
                json.dumps(replacement_config),
                headers=headers(str(rcs.token)),
                pool=self.pool,
            )
            .addCallback(check_success, [204])
            .addCallback(record_results, replacement_config)
        )

    def update_group_config(self, rcs, name=None, cooldown=None,
                            minEntities=None, maxEntities=None, metadata=None):
        """
        Update the group configuration of a scaling group. The provided
        values will be updated, any others will remain unchanged.
        """
        # Get the old config
        old_config = self.get_group_config(rcs)
        new_config = {}

        new_config["name"] = name if name is not None \
            else old_config["name"]
        new_config["cooldown"] = cooldown if cooldown is not None \
            else old_config["cooldown"]
        new_config["minEntities"] = minEntities if minEntities is not None \
            else old_config["minEntities"]
        new_config["maxEntities"] = maxEntities if maxEntities is not None \
            else old_config["maxEntities"]
        new_config["metadata"] = metadata if metadata is not None \
            else old_config["metadata"]

        return self.replace_group_config(rcs, new_config)

    @diagnose("AS", "Triggering convergence")
    def trigger_convergence(self, rcs, success_codes=None):
        """
        Trigger convergence on a group
        """
        d = self.treq.post(
            "{}/converge".format(self._endpoint(rcs)),
            headers=headers(str(rcs.token)), pool=self.pool)
        return d.addCallback(check_success, success_codes or [204])

    @diagnose("AS", "Cleaning up the scaling group")
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
        if getattr(self, 'group_id', None):
            return self.delete_scaling_group(rcs)

    @diagnose("AS", "Deleting scaling group")
    def delete_scaling_group(self, rcs, force="true", success_codes=None):
        """Unconditionally delete the scaling group.  You may call this only
        once.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, upon firing, disposes of the
            scaling group.
        """

        return (self.treq.delete(
            "{}?force={}".format(self._endpoint(rcs), force),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, success_codes or [204, 404]))

    @diagnose("AS", "Getting scaling group state")
    def get_scaling_group_state(self, rcs, success_codes=None):
        """Retrieve the state of the scaling group.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, upon firing, returns the result
            code and, optionally, scaling group state as a 2-tuple, in that
            order.  If not found, the result code will be 404, and the state
            will be None.
        """
        success_codes = [200, 404] if success_codes is None else success_codes

        def decide(resp):
            if resp.code == 200:
                return self.treq.json_content(resp).addCallback(
                    lambda x: (200, x))

            return self.treq.content(resp).addCallback(
                lambda _: (resp.code, None))

        def debug_print(resp_tuple):
            if verbosity > 0:
                print('ScalingGroup.get_scaling_group_state response: ')
                pp.pprint(resp_tuple)
            return resp_tuple

        return (
            self.treq.get(
                "%s/groups/%s/state" % (
                    str(rcs.endpoints["otter"]), self.group_id
                ),
                headers=headers(str(rcs.token)),
                pool=self.pool
            ).addCallback(check_success, success_codes)
            .addCallback(decide)
            .addCallback(debug_print)
        )

    @diagnose("AS", "Creating scaling group")
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
            if verbosity > 0:
                print('Created scaling group {0} \n'.format(self.group_id))
                pp.pprint(rcs.groups)
            return rcs

        return (
            self.treq.post(
                "%s/groups" % str(rcs.endpoints["otter"]),
                json.dumps(self.group_config),
                headers=headers(str(rcs.token)),
                pool=self.pool
            )
            .addCallback(check_success, [201])
            .addCallback(self.treq.json_content)
            .addCallback(record_results)
        )

    @diagnose("AS+Nova", "Getting the servicenet IPs of the active servers")
    def get_servicenet_ips(self, rcs, server_ids=None):
        """
        Get the servicenet IPs for the following server IDs - if no IDs are
        provided, gets the servicenet IPs for all the active servers on the
        group.

        Note that this requires that the nova endpoint already found be on RCS.

        :param rcs: A :class:`otter.integration.lib.resources.TestResources`
            instance.
        :param iterable server_ids: An iterable of server ids - this function
            does not check whether the servers belong the the group

        :return: A mapping of server ID to servicenet address
        :rtype: ``dict``
        """
        def _extract_servicenet_id(server_info):
            private = server_info['addresses'].get('private')
            if private is not None:
                return [addr['addr'] for addr in private
                        if addr['version'] == 4][0]
            return None

        def _get_the_ips(the_server_ids):
            the_server_ids = set(the_server_ids)
            return gatherResults([
                self.server_client(
                    id=server_id, pool=self.pool, treq=self.treq)
                .get_addresses(rcs).addCallback(_extract_servicenet_id)

                for server_id in the_server_ids
            ]).addCallback(lambda results: dict(zip(the_server_ids, results)))

        if server_ids is not None:
            return _get_the_ips(server_ids)

        return (
            self.get_scaling_group_state(rcs, success_codes=[200])
            .addCallback(lambda resp_tuple: resp_tuple[-1])
            .addCallback(extract_active_ids)
            .addCallback(_get_the_ips))

    @diagnose("AS", "Picking random active servers")
    @inlineCallbacks
    def choose_random_servers(self, rcs, n):
        """
        Choose n servers from the active servers on the scaling
        group.
        """
        code, body = yield self.get_scaling_group_state(rcs, [200])

        ids = extract_active_ids(body)
        returnValue(random.sample(ids, n))

    @diagnose("AS", "Pausing scaling group")
    def pause(self, rcs):
        """
        Pause group
        """
        d = self.treq.post(
            "{}/pause".format(self._endpoint(rcs)),
            headers=headers(str(rcs.token)), pool=self.pool)
        return d.addCallback(check_success, [204])

    @diagnose("AS", "Resume scaling group")
    def resume(self, rcs):
        """
        Resume group
        """
        d = self.treq.post(
            "{}/resume".format(self._endpoint(rcs)),
            headers=headers(str(rcs.token)), pool=self.pool)
        return d.addCallback(check_success, [204])

    @diagnose("AS", "Disown server")
    def disown(self, rcs, server_id, purge=False, replace=False):
        """
        Disown a server from the autoscaling group.
        """
        d = self.treq.delete(
            "{0}/servers/{1}".format(self._endpoint(rcs), server_id),
            params={'replace': replace, 'purge': purge},
            headers=headers(str(rcs.token)), pool=self.pool)
        return d.addCallback(check_success, [202])

    @diagnose("AS", "Wait for scaling group state to reach a particular point")
    def wait_for_state(self, rcs, matcher, timeout=600, period=10, clock=None):
        """
        Wait for the state on the scaling group to match the provided matchers,
        specified by matcher.

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance
        :param matcher: A :mod:`testtool.matcher`, as specified in
            module: testtools.matchers in
            http://testtools.readthedocs.org/en/latest/api.html.
        :param timeout: The amount of time to wait until this step is
            considered failed.
        :param period: How long to wait before polling again.
        :param clock: a :class:`twisted.internet.interfaces.IReactorTime`
            provider

        :return: None, if the state is reached
        :raises: :class:`TimedOutError` if the state is never reached within
            the requisite amount of time.

        Example usage:

        ```
        matcher = MatchesAll(
            IncludesServers(included_server_ids),
            ExcludesServers(exclude_server_ids),
            ContainsDict({
                'pending': Equals(0),
                'desired': Equals(5),
                'status': Equals('ACTIVE')
            })
        )

        ..wait_for_state(rcs, matchers, timeout=60)
        ```
        """
        def check(result):
            response, group_state = result
            mismatch = matcher.match(group_state['group'])
            if mismatch:
                msg("Waiting for group {} to reach desired group state.\n"
                    "Mismatch: {}"
                    .format(self.group_id, mismatch.describe()))
                raise TransientRetryError(mismatch.describe())
            msg("Success: desired group state reached:\n{}\nmatches:\n{}"
                .format(group_state['group'], matcher))
            return rcs

        def poll():
            return self.get_scaling_group_state(rcs, [200]).addCallback(check)

        return retry_and_timeout(
            poll, timeout,
            can_retry=terminal_errors_except(TransientRetryError),
            next_interval=repeating_interval(period),
            clock=clock or reactor,
            deferred_description=(
                "Waiting for group {} to reach state {}"
                .format(self.group_id, str(matcher)))
        )

HasActive = MatchesPredicateWithParams(
    lambda state, length: len(state['active']) == length,
    "State {0} does not have {1} active servers."
)
"""
Matcher that asserts something about the number of active servers on the group.
"""

ExcludesServers = MatchesPredicateWithParams(
    lambda state, server_ids:
        not set(server['id'] for server in state['active']).intersection(
            set(server_ids)),
    "State {0} should not contain any of the following server IDs: {1}"
)
"""
Matcher that asserts that all the given server IDs are no longer members of
the scaling group.
"""


@attributes([
    Attribute('scale_by', default_value=None),
    Attribute('scaling_group', instance_of=ScalingGroup),
    Attribute('set_to', default_value=None),
    Attribute('scale_percent', default_value=None),
    Attribute('schedule', default_value=None),
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
    :param dict schedule: "args" argument of policy if this is scheduled
        policy
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
            change_type: change_factor
        }]
        if self.schedule is not None:
            self.policy[0]["type"] = "schedule"
            self.policy[0]["args"] = self.schedule
        else:
            self.policy[0]["type"] = "webhook"

    @diagnose("AS", "Cleaning up policy")
    def stop(self, rcs):
        """Disposes of the policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :return: A :class:`Deferred` which, when triggered, removes the scaling
            policy.  It returns the test resources supplied, easing continuity
            of integration test code.
        """
        if getattr(self, 'policy_id', None):
            return self.delete(rcs)

    @diagnose("AS", "Creating policy")
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

    @diagnose("AS", "Deleting policy")
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

    @diagnose("AS", "Executing policy")
    def execute(self, rcs, success_codes=None):
        """Executes the scaling policy.

        :param TestResources rcs: The integration test resources instance.
            This provides useful information to complete the request, like
            which endpoint to use to make the API request.

        :param iterable success_codes: An iterable of HTTP status codes to
            expect in the success case.  Defaults to 202.

        :return: A :class:`Deferred` which, when triggered, removes the scaling
            policy.  It returns the test resources supplied, easing continuity
            of integration test code.
        """
        return (
            treq.post(
                "%sexecute" % self.link,
                headers=headers(str(rcs.token)),
                pool=self.scaling_group.pool,
            ).addCallback(check_success,
                          [202] if success_codes is None else success_codes)
            # Policy execution does not return anything meaningful,
            # per http://tinyurl.com/ndds6ap (link to docs.rackspace).
            # So, we forcefully return our resources here.
            .addCallback(lambda _, x: x, rcs)
        )

    @diagnose("AS", "Creating webhook")
    def create_webhook(self, rcs):
        """
        Create webhook and return `Webhook` object as Deferred
        """
        d = treq.post(
            "{}/webhooks".format(self.link.rstrip("/")),
            headers=headers(str(rcs.token)),
            data=json.dumps([{"name": "integration-test-webhook"}]),
            pool=self.scaling_group.pool)
        d.addCallback(check_success, [201])
        d.addCallback(treq.json_content)
        return d.addCallback(lambda r: Webhook.from_json(r["webhooks"][0]))


@attributes(["id", "name", "link", "capurl"])
class Webhook(object):
    """
    Scaling group's policy's webhook
    """

    @classmethod
    def from_json(cls, blob):
        return Webhook(
            id=blob["id"], name=blob["name"],
            link=next(str(link["href"]) for link in blob["links"]
                      if link["rel"] == "self"),
            capurl=next(str(link["href"]) for link in blob["links"]
                        if link["rel"] == "capability"))
