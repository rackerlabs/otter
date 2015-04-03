"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

from __future__ import print_function

import json
import os

import treq

from twisted.internet import reactor
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater
from twisted.internet.tcp import Client
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib import autoscale
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources

from otter.util.http import check_success, headers


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']


def find_end_points(rcs):
    """Locates the endpoints we need to conduct convergence tests."""

    rcs.token = rcs.access["access"]["token"]["id"]
    sc = rcs.access["access"]["serviceCatalog"]
    try:
        rcs.endpoints["otter"] = auth.public_endpoint_url(sc,
                                                          "autoscale",
                                                          region)
    except auth.NoSuchEndpoint:
        # If the autoscale endpoint is not defined, use local otter
        rcs.endpoints["otter"] = 'http://localhost:9000/v1.0/{0}'.format(
            rcs.access['access']['token']['tenant']['id'])

    rcs.endpoints["loadbalancers"] = auth.public_endpoint_url(
        sc, "cloudLoadBalancers", region
    )
    rcs.endpoints["nova"] = auth.public_endpoint_url(
        sc, "cloudServersOpenStack", region
    )
    return rcs


def dbg(x, msg):
    print(msg)
    return x


class TestConvergence(unittest.TestCase):
    """This class contains test cases aimed at the Otter Converger."""

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """

        self.pool = HTTPConnectionPool(reactor, False)
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.pool
        )

    def tearDown(self):
        """Destroy the HTTP connection pool, so that we close the reactor
        cleanly.
        """

        def _check_fds(_):
            fds = set(reactor.getReaders() + reactor.getReaders())
            if not [fd for fd in fds if isinstance(fd, Client)]:
                return
            return deferLater(reactor, 0, _check_fds, None)
        return self.pool.closeCachedConnections().addBoth(_check_fds)

    def test_reaction_to_oob_server_deletion(self):
        """Exercise out-of-band server deletion.  The goal is to spin up, say,
        eight servers, then use Nova to delete four of them.  We should be able
        to see, over time, more servers coming into existence to replace those
        deleted.
        """

        N_SERVERS = 2

        rcs = TestResources()

        def choose_half_the_servers(t):
            if t[0] != 200:
                raise Exception("Got 404; where'd the scaling group go?")
            ids = map(lambda obj: obj['id'], t[1]['group']['active'])
            return ids[:(len(ids) / 2)]

        def delete_server_by_id(i):
            print("{}/servers/{}".format(str(rcs.endpoints["nova"]), i))
            return (
                treq.delete(
                    "{}/servers/{}".format(str(rcs.endpoints["nova"]), i),
                    headers=headers(str(rcs.token)),
                    pool=self.pool
                ).addCallback(check_success, [204])
                .addCallback(lambda _: rcs)
            )

        def delete_those_servers(ids):
            deferreds = map(lambda i: delete_server_by_id(i), ids)
            # If no error occurs while deleting, all the results will be the
            # same.  So just return the 1st, which is just our rcs value.
            return gatherResults(deferreds).addCallback(lambda rslts: rslts[0])

        scaling_group_body = {
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
                "name": "converger-test-configuration",
                "cooldown": 0,
                "minEntities": N_SERVERS,
            },
            "scalingPolicies": [],
        }

        self.scaling_group = autoscale.ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        d = (
            self.identity.authenticate_user(rcs)
            .addCallback(dbg, "find_end_points")
            .addCallback(find_end_points)
            .addCallback(dbg, "scaling_group.start")
            .addCallback(self.scaling_group.start, self)
            .addCallback(dbg, "wait for N_SERVERS")
            .addCallback(
                self.scaling_group.wait_for_N_servers, N_SERVERS, timeout=1800
            ).addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(dbg, "choose_half_the_servers")
            .addCallback(choose_half_the_servers)
            .addCallback(dbg, "delete_those_servers")
            .addCallback(delete_those_servers)
            .addCallback(dbg, "get_scaling_group_state")
            .addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(dbg, "print")
            .addCallback(lambda x: print(json.dumps(x, indent=4)))
            .addCallback(dbg, "done")
        )
        return d
    test_reaction_to_oob_server_deletion.timeout = 600
