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


def find_end_point(rcs):
    rcs.token = rcs.access["access"]["token"]["id"]
    sc = rcs.access["access"]["serviceCatalog"]
    rcs.endpoints["otter"] = auth.public_endpoint_url(sc, "autoscale", "IAD")
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
            .addCallback(dump_groups)
        )
        return d
