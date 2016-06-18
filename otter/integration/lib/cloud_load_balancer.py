"""Contains reusable classes and utilities relating to cloud load balancers."""

from __future__ import print_function

import json

from functools import partial, wraps

from characteristic import Attribute, attributes

from testtools.matchers import MatchesPredicateWithParams

import treq

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.log import msg

from otter.integration.lib.utils import diagnose

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import APIError, UpstreamError, check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    terminal_errors_except
)


def _pending_update_to_transient(f):
    """
    A cloud load balancer locks on every update, so to ensure that the test
    doesn't fail because of that, we want to retry POST/PUT/DELETE commands
    issued by the test.  This is a utility function that checks if a treq
    API failure is a 422 PENDING_UDPATE failure, and if so, re-raises a
    TransientRetryError instead.
    """
    f.trap(UpstreamError, APIError)
    if f.check(UpstreamError):
        return _pending_update_to_transient(f.value.reason)
    if f.value.code == 422 and 'PENDING_UPDATE' in f.value.body:
        raise TransientRetryError()
    return f


def _retry(reason, timeout=60, period=3, clock=reactor):
    """
    Helper that decorates a function to retry it until success it succeeds or
    times out.  Assumes the function will raise :class:`TransientRetryError`
    if it can be retried.
    """
    def decorator(f):
        @wraps(f)
        def retrier(*args, **kwargs):
            return retry_and_timeout(
                partial(f, *args, **kwargs), timeout,
                can_retry=terminal_errors_except(TransientRetryError),
                next_interval=repeating_interval(period),
                clock=clock,
                deferred_description=reason
            )
        return retrier
    return decorator


@attributes([
    Attribute('pool', default_value=None),
    Attribute('treq', default_value=treq)
])
class CloudLoadBalancer(object):
    """The CloudLoadBalancer class represents a Rackspace Cloud Load Balancer
    resource.
    """
    def config(self):
        """Returns the JSON structure (as a Python dictionary) used to
        configure the cloud load balancer via API operations.
        """
        return {
            "loadBalancer": {
                "name": "a-load-balancer",
                "port": 80,
                "protocol": "HTTP",
                # this algorithm is chosen otherwise we won't be able to
                # check the weights on the nodes by listing all the nodes
                "algorithm": "WEIGHTED_ROUND_ROBIN",
                "virtualIps": [{
                    "type": "PUBLIC",
                    "ipVersion": "IPV6",
                }],
            }
        }

    def scaling_group_spec(self, port=80):
        """Computes the necessary CLB specification to use when creating a
        scaling group.  See also the lib.autoscale.create_scaling_group_dict
        function for more details.
        """
        return {
            "port": port,
            "loadBalancerId": self.clb_id,
        }

    def endpoint(self, rcs):
        """
        :param TestResources rcs: The resources used to make appropriate API
            calls with.

        :return: this load balancer's endpoint
        """
        return "{0}/loadbalancers/{1}".format(
            str(rcs.endpoints['loadbalancers']), self.clb_id)

    @diagnose("clb", "Getting the CLB state")
    def get_state(self, rcs):
        """Returns the current state of the cloud load balancer.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        :return: A `Deferred` which, when fired, returns the parsed JSON for
            the current cloud load balancer state.
        """
        return (
            self.treq.get(
                self.endpoint(rcs),
                headers=headers(str(rcs.token)),
                pool=self.pool,
            )
            .addCallback(check_success, [200], _treq=self.treq)
            .addCallback(self.treq.json_content)
        )

    @diagnose("clb", "Wait for CLB to achieve a particular status")
    def wait_for_state(
        self, rcs, state_desired, timeout, period=10, clock=reactor
    ):
        """
        Wait for the cloud load balancer to reach a certain state.  After
        a timeout, a `TimeoutError` exception will occur.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        :param str state_desired: The state you expect the cloud load balancer
            to eventually reach.
        :param int timeout: The number of seconds to wait before timing out.
        :param int period: The number of seconds between polls to the cloud
            load balancer.  If left unspecified, it defaults to 10 seconds.
        :param twisted.internet.interfaces.IReactorTime clock: If provided,
            the clock to use for scheduling things.  Defaults to `reactor`
            if not specified.
        :result: A `Deferred` which if fired, returns the same test resources
            as provided this method.  This signifies the state has been
            reached.  If the state has not been attained in the timeout period,
            an exception will be raised, which can be caught in an Errback.
        """
        def check(state):
            lb_state = state["loadBalancer"]["status"]
            if lb_state == state_desired:
                return rcs

            raise TransientRetryError()

        @_retry("Waiting for cloud load balancer to reach state {}".format(
                state_desired),
                timeout=timeout, period=period, clock=clock)
        def poll():
            return self.get_state(rcs).addCallback(check)

        return poll()

    @diagnose("clb", "Cleaning up CLB")
    def stop(self, rcs):
        """Stops and deletes the cloud load balancer.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        """
        if getattr(self, 'clb_id', None):
            return self.delete(rcs).addErrback(
                lambda f: msg("error cleaning up clb: {}".format(f)))

    @diagnose("clb", "Creating CLB")
    def start(self, rcs, test):
        """Creates the cloud load balancer and launches it in the cloud.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        :param twisted.trial.unittest.TestCase test: The test case running the
            integration test.
        :return: A `Deferred` which, when fired, returns the resources provided
            to the `start` function.  The instance will also have its cloud
            load balancer ID (`clb_id`) set by this time.
        """
        test.addCleanup(self.stop, rcs)

        def record_results(resp):
            rcs.clbs.append(resp)
            self.clb_id = str(resp["loadBalancer"]["id"])
            return rcs

        return (self.treq.post("%s/loadbalancers" %
                               str(rcs.endpoints["loadbalancers"]),
                               json.dumps(self.config()),
                               headers=headers(str(rcs.token)),
                               pool=self.pool)
                .addCallback(check_success, [202], _treq=self.treq)
                .addCallback(self.treq.json_content)
                .addCallback(record_results))

    @diagnose("clb", "Deleting CLB")
    def delete(self, rcs, clock=reactor):
        """
        Delete the cloud load balancer.  This might not work due to the load
        balancer being in an immutable state, but the error returned from
        attempting the delete does not tell us which immutable state it is in.

        So we also want to do a get, to see if we have to try again.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        """
        @_retry("Trying to delete CLB", clock=clock)
        @inlineCallbacks
        def really_delete():
            yield self.treq.delete(
                self.endpoint(rcs),
                headers=headers(str(rcs.token)),
                pool=self.pool,
            ).addCallback(self.treq.content)

            try:
                state = yield self.get_state(rcs)
            except UpstreamError as e:
                if not e.reason.check(APIError) or e.reason.value.code != 404:
                    raise e
            else:
                if state['loadBalancer']['status'] not in (
                        "PENDING_DELETE", "SUSPENDED", "ERROR", "DELETED"):
                    raise TransientRetryError()
                if state['loadBalancer']['status'] in ("ERROR", "SUSPENDED"):
                    msg("Could not delete CLB {0} because it is in {1} state, "
                        "but considering this good enough.".format(
                            self.clb_id, state['loadBalancer']['status']))

        return really_delete()

    @diagnose("clb", "Listing nodes")
    def list_nodes(self, rcs):
        """
        Get all the nodes on the load balancer.

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance

        :return: the JSON response from the load balancer, which looks like::

            {
                "nodes": [
                    {
                        "id": ...
                    },
                    {
                        "id": ...
                    },
                    ...
                ]
            }

        """
        d = self.treq.get(
            "{0}/nodes".format(self.endpoint(rcs)),
            headers=headers(str(rcs.token)),
            pool=self.pool
        )
        d.addCallback(check_success, [200], _treq=self.treq)
        d.addCallback(self.treq.json_content)
        return d

    @diagnose("clb", "Waiting for CLB nodes to reach a particular state")
    def wait_for_nodes(self, rcs, matcher, timeout, period=10, clock=reactor):
        """
        Wait for the nodes on the load balancer to reflect a certain state,
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

        :return: the list of nodes, if the state is reached
        :raises: :class:`TimedOutError` if the state is never reached within
            the requisite amount of time.

        Example usage:

        ```
        matcher = MatchesAll(
            ExcludesAllIPs(excluded_ips)),
            ContainsAllIps(included_ips),
            HasLength(5)
        )

        ..wait_for_nodes(rcs, matchers, timeout=60)
        ```
        """
        def check(nodes):
            mismatch = matcher.match(nodes["nodes"])
            if mismatch:
                msg("Waiting for CLB node state for CLB {}.\nMismatch: {}"
                    .format(self.clb_id, mismatch.describe()))
                raise TransientRetryError(mismatch.describe())
            return nodes['nodes']

        @_retry("Waiting for nodes to reach state {0}".format(str(matcher)),
                timeout=timeout, period=period, clock=clock)
        def poll():
            return self.list_nodes(rcs).addCallback(check)

        return poll()

    @diagnose("clb", "Updating a CLB node")
    def update_node(self, rcs, node_id, weight=None, condition=None,
                    type=None, clock=reactor):
        """
        Update a node's attributes.  At least one of the optional parameters
        must be provided.

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance

        :param node_id: The node ID to modify
        :type node_id: `str` or `int`

        :param int weight: The weight to change the node to
        :param str condition: The condition to change the node to - one of
            ENABLED, DISBABLED, or DRAINING.
        :param str type: The type to change the node to - one of PRIMARY or
            SECONDARY

        :return: An empty string if successful.
        """
        data = [("weight", weight), ("condition", condition), ("type", type)]
        data = {k: v for k, v in data if v is not None}

        @_retry("Trying to change node {0}".format(node_id), clock=clock)
        def really_change():
            d = self.treq.put(
                "{0}/nodes/{1}".format(self.endpoint(rcs), node_id),
                json.dumps({"node": data}),
                headers=headers(str(rcs.token)),
                pool=self.pool
            )
            d.addCallback(check_success, [202], _treq=self.treq)
            d.addCallbacks(self.treq.content, _pending_update_to_transient)
            return d

        return really_change()

    @diagnose("clb", "Deleting CLB nodes")
    def delete_nodes(self, rcs, node_ids, clock=reactor):
        """
        Delete one or more nodes from a load balancer.

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance

        :param list node_ids: A list of `int` node ids to delete.

        :return: An empty string if successful.
        """
        @_retry("Trying to delete nodes {0}".format(
                ", ".join(map(str, node_ids))),
                clock=clock)
        def really_delete():
            d = self.treq.delete(
                "{0}/nodes".format(self.endpoint(rcs)),
                params=[('id', node_id) for node_id in node_ids],
                headers=headers(str(rcs.token)),
                pool=self.pool
            )
            d.addCallback(check_success, [202], _treq=self.treq)
            d.addCallbacks(self.treq.content, _pending_update_to_transient)
            return d

        return really_delete()

    @diagnose("clb", "Adding CLB nodes")
    def add_nodes(self, rcs, node_list, clock=reactor):
        """
        Add one or more nodes to a cloud load balancer

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance

        :param list node_list: A list of node dictionaries to add.

        :return: On success, a json dictionary containing the add response that
            lists the nodes

        """
        @_retry("Trying to add nodes.", clock=clock)
        def really_add():
            d = self.treq.post(
                "{0}/nodes".format(self.endpoint(rcs)),
                json.dumps({"nodes": node_list}),
                headers=headers(str(rcs.token)),
                pool=self.pool
            )
            d.addCallback(check_success, [202], _treq=self.treq)
            d.addCallbacks(self.treq.json_content,
                           _pending_update_to_transient)
            return d

        return really_add()

    @diagnose("clb", "Updating health monitor")
    def update_health_monitor(self, rcs, config, clock=reactor):
        """
        Update health monitor configuration

        :param rcs: a :class:`otter.integration.lib.resources.TestResources`
            instance
        :param dict config: Health monitor configuration that will be sent as
            {"healthMonitor": config"}

        :return: On success, Deferred fired with None
        """

        @_retry("Trying to update health monitor.", clock=clock)
        def try_update():
            d = self.treq.put(
                "{}/healthmonitor".format(self.endpoint(rcs)),
                json.dumps({"healthMonitor": config}),
                headers=headers(str(rcs.token)),
                pool=self.pool)
            d.addCallback(check_success, [202], _treq=self.treq)
            d.addCallbacks(self.treq.content, _pending_update_to_transient)
            return d.addCallback(lambda _: None)

        return try_update()


HasLength = MatchesPredicateWithParams(
    lambda items, length: len(items) == length,
    "len({0}) is not {1}"
)
"""
Matcher that asserts something about the number of items.
"""

ExcludesAllIPs = MatchesPredicateWithParams(
    lambda nodes, ips: not set(node['address'] for node in nodes).intersection(
        set(ips)),
    "The nodes {0} should not contain any of the following IP addresses: {1}"
)
"""
Matcher that asserts that all the given IPs are no longer on the load balancer.
"""

ContainsAllIPs = MatchesPredicateWithParams(
    lambda nodes, ips: set(ips).issubset(
        set(node['address'] for node in nodes)),
    "The nodes {0} should have all of the following IP addresses: {1}"
)
"""
Matcher that asserts that all the given IPs are on the load balancer.
"""
