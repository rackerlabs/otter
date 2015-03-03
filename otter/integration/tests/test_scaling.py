"""A quick trial-based test to exercise scale-up and scale-down functionality.
"""

# TODO(sfalvo): Scale-up functionality isn't finished yet.  I'll finish this
# after refactoring is done.
#
# TODO(sfalvo): Scale-down functionality isn't implemented yet.  I'll finish
# this after refactoring is done.


from __future__ import print_function

import json
import os

from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.internet.tcp import Client
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib import autoscale
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources


from characteristic import attributes, Attribute
import treq
from otter.util.http import check_success, headers
from twisted.internet.task import LoopingCall


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']


def dump_js(js):
    print(json.dumps(js, indent=4))


def dump_groups(rcs):
    for g in rcs.groups:
        dump_js(g)
    return rcs


def dump_state(s):
    dump_js(s)


def find_end_point(rcs):
    rcs.token = rcs.access["access"]["token"]["id"]
    sc = rcs.access["access"]["serviceCatalog"]
    rcs.endpoints["otter"] = auth.public_endpoint_url(sc, "autoscale", region)
    rcs.endpoints["loadbalancers"] = auth.public_endpoint_url(sc, "cloudLoadBalancers", region)
    return rcs


def print_token_and_ep(rcs):
    print("TOKEN(%s) EP(%s)" % (rcs.token, rcs.endpoints["otter"]))
    return rcs


class TestScaling(unittest.TestCase):
    def setUp(self):
        self.pool = HTTPConnectionPool(reactor, False)
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.pool
        )

    def tearDown(self):
        def _check_fds(_):
            fds = set(reactor.getReaders() + reactor.getReaders())
            if not [fd for fd in fds if isinstance(fd, Client)]:
                return
            return deferLater(reactor, 0, _check_fds, None)
        return self.pool.closeCachedConnections().addBoth(_check_fds)

    def test_scaling_up(self):
        group_configuration = {
            "name": "my-group-configuration",
            "cooldown": 0,
            "minEntities": 0,
        }
        launch_configuration = {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": flavor_ref,
                    "imageRef": image_ref,
                }
            }
        }
        scaling_group_body = {
            "launchConfiguration": launch_configuration,
            "groupConfiguration": group_configuration,
            "scalingPolicies": [],
        }

        self.scaling_group = autoscale.ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.scaling_policy = autoscale.ScalingPolicy(
            scale_by=2,
            scaling_group=self.scaling_group
        )

        rcs = TestResources()
        d = (
            self.identity.authenticate_user(rcs)
            .addCallback(find_end_point)
            .addCallback(print_token_and_ep)
            .addCallback(self.scaling_group.start, self)
            .addCallback(dump_groups)
            .addCallback(self.scaling_policy.start, self)
            .addCallback(self.scaling_policy.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers, 2, timeout=1800
            ).addCallback(
                lambda _: self.scaling_group.get_scaling_group_state(rcs)
            ).addCallback(dump_state)
        )
        return d
    test_scaling_up.timeout = 1800

    def test_policy_execution_after_adding_clb(self):
        rcs = TestResources()

        self.clb1 = CloudLoadBalancer(pool=self.pool)

        def finish_setup(x, self):
            scaling_group_body = {
                "launchConfiguration": {
                    "type": "launch_server",
                    "args": {
                        "loadbalancers": [{
                            "port": 80,
                            "loadBalancerId": self.clb1.clb_id,
                        }],
                        "server": {
                            "flavorRef": flavor_ref,
                            "imageRef": image_ref,
                        }
                    }
                },
                "groupConfiguration": {
                    "name": "my-group-configuration",
                    "cooldown": 0,
                    "minEntities": 0,
                },
                "scalingPolicies": [],
            }

            self.scaling_group = autoscale.ScalingGroup(
                group_config=scaling_group_body,
                pool=self.pool
            )

            self.scale_up_policy = autoscale.ScalingPolicy(
                scale_by=2,
                scaling_group=self.scaling_group
            )

            self.scale_down_policy = autoscale.ScalingPolicy(
                scale_by=-2,
                scaling_group=self.scaling_group
            )

            d = (
                self.scaling_group.start(rcs, self)
                .addCallback(self.scaling_group.start, self)
                .addCallback(self.scale_up_policy.start, self)
                .addCallback(self.scale_down_policy.start, self)
            )
            return d

        d = (
            self.identity.authenticate_user(rcs)
            .addCallback(find_end_point)
            .addCallback(self.clb1.start, self)
            .addCallback(self.clb1.wait_for_state, "ACTIVE", 600)
        ).addCallback(finish_setup, self)
        return d

    test_policy_execution_after_adding_clb.timeout = 1800


@attributes([
    Attribute('pool', default_value=None),
])
class CloudLoadBalancer(object):
    def config(self):
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

    def get_state(self, rcs):
        return (
            treq.get(
                "%s/loadbalancers/%s" % (
                    str(rcs.endpoints["loadbalancers"]),
                    self.clb_id
                ),
                headers = headers(str(rcs.token)),
                pool = self.pool,
            )
            .addCallback(check_success, [200])
            .addCallback(treq.json_content)
        )

    def wait_for_state(self, rcs, state_desired, timeout, period=10, clock=None):
        clock = clock or reactor

        class Looper(object):
            def __init__(self, load_balancer):
                self.elapsed_time = 0
                self.load_balancer = load_balancer
                # To be filled in later.
                self.loopingCall = None

            def loop(self):
                if self.elapsed_time < timeout:
                    self.elapsed_time += period
                    return self.check_load_balancer()
                else:
                    raise TimeoutError(
                        "Spent %ds, polling every %ds, timeout." % (
                            self.elapsed_time, period
                        )
                    )

            def check_status(self, state_results):
                lb_state = state_results["loadBalancer"]["status"]
                if lb_state == state_desired:
                    self.loopingCall.stop()

            def check_load_balancer(self):
                d = (self.load_balancer.get_state(rcs)
                     .addCallback(self.check_status))
                return d

        looper = Looper(self)
        lc = LoopingCall(looper.loop)
        lc.clock = clock
        looper.loopingCall = lc
        d = lc.start(period).addCallback(lambda _: rcs)
        return d

    def stop(self, rcs):
        return self.delete(rcs)

    def start(self, rcs, test):
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
