"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

import os

import treq

from twisted.internet import reactor
from twisted.internet.defer import gatherResults
from twisted.internet.task import deferLater
from twisted.internet.tcp import Client
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib.autoscale import (
    BreakLoopException,
    ScalingGroup,
    ScalingPolicy,
)
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    transient_errors_except,
)


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

        N_SERVERS = 4

        rcs = TestResources()

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

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.scaling_policy = ScalingPolicy(
            scale_by=1,
            scaling_group=self.scaling_group
        )

        def exercise_converger():
            """The test works by spinning up a scaling group with N_SERVERS.
            After that's done, we delete half the servers created directly via
            Nova.  We then perform a scaling policy operation to convince the
            Autoscale Converger to take action on this tenant, and we wait.

            If convergence is doing its job, we should see half the number of
            servers in the ``active`` list returned by
            ``get_scaling_group_state``.  If we timeout before this happens,
            either Autoscale is *really* busy, convergence isn't enabled for
            this tenant, or it's just not working.  In any of these cases,
            human intervention should be sought.
            """

            d = (
                self.identity.authenticate_user(rcs)
                .addCallback(find_end_points)
                .addCallback(self.scaling_group.start, self)
                .addCallback(
                    self.scaling_group.wait_for_N_servers,
                    N_SERVERS, timeout=1800
                ).addCallback(self.scaling_group.get_scaling_group_state)
                .addCallback(self._choose_half_the_servers)
                .addCallback(self._delete_those_servers, rcs)
                .addCallback(self.scaling_policy.start, self)
                .addCallback(self.scaling_policy.execute)
                .addCallback(self._wait_for_autoscale_to_catch_up, rcs)
            )
            return d

        return exercise_converger()
    test_reaction_to_oob_server_deletion.timeout = 600

    def _choose_half_the_servers(self, t):
        """Select the first half of the servers returned by the
        ``get_scaling_group_state`` function.  Record the number of servers
        received in ``n_servers`` attribute, and the number killed (which
        should be roughly half) in ``n_killed``.
        """

        if t[0] != 200:
            raise Exception("Got 404; where'd the scaling group go?")
        ids = map(lambda obj: obj['id'], t[1]['group']['active'])
        self.n_servers = len(ids)
        self.n_killed = self.n_servers / 2
        return ids[:self.n_killed]

    def _delete_those_servers(self, ids, rcs):
        """Delete each of the servers selected."""

        def delete_server_by_id(i):
            return (
                treq.delete(
                    "{}/servers/{}".format(str(rcs.endpoints["nova"]), i),
                    headers=headers(str(rcs.token)),
                    pool=self.pool
                ).addCallback(check_success, [204])
                .addCallback(lambda _: rcs)
            )

        deferreds = map(delete_server_by_id, ids)
        # If no error occurs while deleting, all the results will be the
        # same.  So just return the 1st, which is just our rcs value.
        return gatherResults(deferreds).addCallback(lambda rslts: rslts[0])

    def _wait_for_autoscale_to_catch_up(self, _, rcs, timeout=60, period=1):
        """Wait for the converger to recognize the reality of this tenant's
        situation and reflect it in the scaling group state accordingly.
        """

        def check(state):
            if state[0] != 200:
                raise BreakLoopException(
                    "Scaling group appears to have disappeared"
                )

            # Our scaling policy (see above) is configured to scale up by 1
            # server.  Thus, we check to see if our server quantity equals
            # the remaining servers plus 1.

            n_remaining = self.n_servers - self.n_killed + 1
            if len(state[1]["group"]["active"]) == n_remaining:
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
                "Waiting for Autoscale to see we killed {} servers of "
                "{}.".format(self.n_killed, self.n_servers)
            )
        )
