"""Contains reusable classes relating to autoscale."""

from __future__ import print_function

import json

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


@attributes([
    Attribute('pool', default_value=None),
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
                "virtualIps": [{
                    "type": "PUBLIC",
                    "ipVersion": "IPV6",
                }],
            }
        }

    def scaling_group_spec(self):
        """Computes the necessary CLB specification to use when creating a
        scaling group.  See also the lib.autoscale.create_scaling_group_dict
        function for more details.
        """

        return {
            "port": 80,
            "loadBalancerId": self.clb_id,
        }

    def get_state(self, rcs):
        """Returns the current state of the cloud load balancer.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        :return: A `Deferred` which, when fired, returns the parsed JSON for
            the current cloud load balancer state.
        """
        return (
            treq.get(
                "%s/loadbalancers/%s" % (
                    str(rcs.endpoints["loadbalancers"]),
                    self.clb_id
                ),
                headers=headers(str(rcs.token)),
                pool=self.pool,
            )
            .addCallback(check_success, [200])
            .addCallback(treq.json_content)
        )

    def wait_for_state(
        self, rcs, state_desired, timeout, period=10, clock=None
    ):
        """Waits for the cloud load balancer to reach a certain state.  After
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

        def poll():
            return self.get_state(rcs).addCallback(check)

        return retry_and_timeout(
            poll, timeout,
            can_retry=transient_errors_except(),
            next_interval=repeating_interval(period),
            clock=clock or reactor,
            deferred_description=(
                "Waiting for cloud load balancer to reach state {}".format(
                    state_desired
                )
            )
        )

    def stop(self, rcs):
        """Stops and deletes the cloud load balancer.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        """
        return self.delete(rcs)

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
            print(resp)
            rcs.clbs.append(resp)
            self.clb_id = str(resp["loadBalancer"]["id"])
            return rcs

        return (treq.post("%s/loadbalancers" %
                          str(rcs.endpoints["loadbalancers"]),
                          json.dumps(self.config()),
                          headers=headers(str(rcs.token)),
                          pool=self.pool)
                .addCallback(check_success, [202])
                .addCallback(treq.json_content)
                .addCallback(record_results))

    def delete(self, rcs):
        """Stops and deletes the cloud load balancer.

        :param TestResources rcs: The resources used to make appropriate API
            calls with.
        """
        return (
            treq.delete(
                "%s/loadbalancers/%s" % (
                    str(rcs.endpoints["loadbalancers"]),
                    self.clb_id
                ),
                headers=headers(str(rcs.token)),
                pool=self.pool
            ).addCallback(check_success, [202, 404])
        ).addCallback(lambda _: rcs)
