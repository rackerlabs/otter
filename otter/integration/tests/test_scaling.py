"""A quick trial-based test to exercise scale-up and scale-down functionality.
"""

from __future__ import print_function

import json
import os

from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.internet.tcp import Client
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib import autoscale, cloud_load_balancer
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources


skip = "This module needs maintenance before being run."


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


def print_endpoints(rcs):
    print(rcs.endpoints)
    return rcs


def dump_state(s):
    dump_js(s)


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
        scaling_group_body = autoscale.create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            name="my-group-configuration"
        )

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
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                    "loadbalancers": ("cloudLoadBalancers",),
                },
                region=region,
            ).addCallback(print_token_and_ep)
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

    def test_scaling_down(self):
        """
        Verify that a basic scale down operation completes as expected.
        """
        scaling_group_body = autoscale.create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            name="tr-scaledown-conf",
        )

        self.scaling_group = autoscale.ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.scaling_policy_up_2 = autoscale.ScalingPolicy(
            scale_by=2,
            scaling_group=self.scaling_group
        )
        self.scaling_policy_down_1 = autoscale.ScalingPolicy(
            scale_by=-1,
            scaling_group=self.scaling_group
        )

        rcs = TestResources()
        d = (
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                    "loadbalancers": ("cloudLoadBalancers",),
                },
                region=region
            ).addCallback(print_token_and_ep)
            .addCallback(self.scaling_group.start, self)
            .addCallback(self.scaling_policy_up_2.start, self)
            .addCallback(self.scaling_policy_up_2.execute)
            .addCallback(self.scaling_group.wait_for_N_servers,
                         2, timeout=1800)
            .addCallback(
                lambda _: self.scaling_group.get_scaling_group_state(rcs))
            .addCallback(dump_state)
            .addCallback(lambda _: rcs)
            .addCallback(self.scaling_policy_down_1.start, self)
            .addCallback(self.scaling_policy_down_1.execute)
            .addCallback(self.scaling_group.wait_for_N_servers,
                         1, timeout=900)
            .addCallback(
                lambda _: self.scaling_group.get_scaling_group_state(rcs)
            ).addCallback(dump_state)
        )
        return d
    test_scaling_down.timeout = 2700

    def test_policy_execution_after_adding_clb(self):
        """This test attempts to reproduce the steps documented in a bug
        submitted to Otter, documented in
        https://github.com/rackerlabs/otter/issues/1135
        """
        rcs = TestResources()

        def create_1st_load_balancer():
            """First, we authenticate and create a single load balancer."""
            self.clb1 = cloud_load_balancer.CloudLoadBalancer(pool=self.pool)

            return (
                self.identity.authenticate_user(
                    rcs,
                    resources={
                        "otter": (
                            "autoscale", "http://localhost:9000/v1.0/{0}"
                        ),
                        "loadbalancers": ("cloudLoadBalancers",),
                    },
                    region=region
                ).addCallback(self.clb1.start, self)
                .addCallback(self.clb1.wait_for_state, "ACTIVE", 600)
            ).addCallback(add_2nd_load_balancer, self)

        def add_2nd_load_balancer(_, self):
            """After that, we scale up to two servers, then create the second
            load balancer.
            """
            self.clb2 = cloud_load_balancer.CloudLoadBalancer(pool=self.pool)

            scaling_group_body = {
                "launchConfiguration": {
                    "type": "launch_server",
                    "args": {
                        "loadBalancers": [{
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
                .addCallback(self.scale_up_policy.start, self)
                .addCallback(self.scale_down_policy.start, self)
                .addCallback(self.scale_up_policy.execute)
                .addCallback(self.scaling_group.wait_for_N_servers, 2,
                             timeout=1800)
                .addCallback(self.clb2.start, self)
                .addCallback(self.clb2.wait_for_state, "ACTIVE", 600)
            ).addCallback(scale_after_lc_changed, self)
            return d

        def scale_after_lc_changed(_, self):
            """After that, we attempt to execute a scaling policy (doesn't
            matter which one).  According to the bug report, this yields an
            error.
            """
            lc_alt = {
                "type": "launch_server",
                "args": {
                    "loadBalancers": [{
                        "port": 80,
                        "loadBalancerId": self.clb1.clb_id,
                    }, {
                        "port": 80,
                        "loadBalancerId": self.clb2.clb_id,
                    }],
                    "server": {
                        "flavorRef": flavor_ref,
                        "imageRef": image_ref,
                    }
                }
            }
            d = (
                self.scaling_group.set_launch_config(rcs, lc_alt)
                .addCallback(self.scale_down_policy.execute)
                .addCallback(self.scaling_group.wait_for_N_servers, 0,
                             timeout=1800)
            )
            return d

        return create_1st_load_balancer()
    test_policy_execution_after_adding_clb.timeout = 1800
