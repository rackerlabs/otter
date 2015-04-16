"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

import os
import random

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
    create_scaling_group_dict,
)
from otter.integration.lib.cloud_load_balancer import CloudLoadBalancer
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
            fds = set(reactor.getReaders() + reactor.getWriters())
            if not [fd for fd in fds if isinstance(fd, Client)]:
                return
            return deferLater(reactor, 0, _check_fds, None)
        return self.pool.closeCachedConnections().addBoth(_check_fds)

    def test_scaling_to_clb_max_after_oob_delete_type1(self):
        """This test starts with a scaling group with no servers.  We scale up
        to 24 servers, but after that's done, we delete 2 directly through
        Nova.  After that, we scale up once more by 1 server, thus max'ing out
        the CLB's ports.  We expect that the group will return to 25 servers,
        and does not overshoot in the process.

        Further, we want to make sure the deleted servers are removed from the
        CLB.
        """

        rcs = TestResources()

        def create_clb_first():
            self.clb = CloudLoadBalancer(pool=self.pool)
            return (
                self.identity.authenticate_user(rcs)
                .addCallback(
                    rcs.find_end_point,
                    "otter", "autoscale", region,
                    default_url='http://localhost:9000/v1.0/{0}'
                ).addCallback(
                    rcs.find_end_point,
                    "nova", "cloudServersOpenStack", region
                ).addCallback(
                    rcs.find_end_point,
                    "loadbalancers", "cloudLoadBalancers", region
                ).addCallback(self.clb.start, self)
                .addCallback(self.clb.wait_for_state, "ACTIVE", 600)
            )

        def then_test(_):
            scaling_group_body = create_scaling_group_dict(
                image_ref=image_ref, flavor_ref=flavor_ref,
                use_lbs=[self.clb.scaling_group_spec()],
            )

            self.scaling_group = ScalingGroup(
                group_config=scaling_group_body,
                pool=self.pool
            )

            self.first_scaling_policy = ScalingPolicy(
                scale_by=24,
                scaling_group=self.scaling_group
            )

            # If we didn't have this policy, then this test would always pass
            # on an Otter deployment w/out Convergence enabled.  Reason: we
            # start off with 24 servers.  We OOB-delete 2 of them, leaving 22
            # actually running; however, Otter will still think 24 exist.  We
            # scale up by one, and:
            #
            # - If Otter doesn't converge, then it'll just spin up another
            # server, and will meet the test criteria, OR,
            #
            # - If Otter converges, it's entirely possible for it to notice
            # that two servers are gone, for it to attempt to provision
            # replacements, and then provision the third and final server, all
            # before we get a response back from
            # scaling_group.get_scaling_group_state.
            #
            # So, we need an intermediate step that *guarantees* our test the
            # ability to inspect Otter's behavior.  This is that step.
            self.second_scaling_policy = ScalingPolicy(
                scale_by=-1,
                scaling_group=self.scaling_group
            )

            # We scale up by 2 here instead of 1, to make up for the -1 in the
            # previous scaling policy.
            self.third_scaling_policy = ScalingPolicy(
                scale_by=2,
                scaling_group=self.scaling_group
            )

            return (
                self.scaling_group.start(rcs, self)
                .addCallback(self.first_scaling_policy.start, self)
                .addCallback(self.second_scaling_policy.start, self)
                .addCallback(self.third_scaling_policy.start, self)
                .addCallback(self.first_scaling_policy.execute)
                .addCallback(
                    self.scaling_group.wait_for_N_servers, 24, timeout=1800
                ).addCallback(self.scaling_group.get_scaling_group_state)
                .addCallback(self._choose_random_servers, 2)
                .addCallback(self._delete_those_servers, rcs)
                .addCallback(self.second_scaling_policy.execute)
                .addCallback(
                    self._wait_for_autoscale_to_catch_up, rcs, delta=-1
                )
                .addCallback(self.third_scaling_policy.execute)
                .addCallback(
                    self.scaling_group.wait_for_N_servers, 25, timeout=1800
                )
            )

        return create_clb_first().addCallback(then_test)
    test_scaling_to_clb_max_after_oob_delete_type1.timeout = 1800

    def test_reaction_to_oob_server_deletion(self):
        """Exercise out-of-band server deletion.  The goal is to spin up, say,
        eight servers, then use Nova to delete four of them.  We should be able
        to see, over time, more servers coming into existence to replace those
        deleted.
        """

        N_SERVERS = 4

        rcs = TestResources()

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=N_SERVERS
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.scaling_policy = ScalingPolicy(
            scale_by=1,
            scaling_group=self.scaling_group
        )

        return (
            self.identity.authenticate_user(rcs)
            .addCallback(
                rcs.find_end_point,
                "otter", "autoscale", region,
                default_url='http://localhost:9000/v1.0/{0}'
            ).addCallback(
                rcs.find_end_point,
                "nova", "cloudServersOpenStack", region
            ).addCallback(self.scaling_group.start, self)
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
    test_reaction_to_oob_server_deletion.timeout = 600

    def _choose_half_the_servers(self, (code, response)):
        """Select the first half of the servers returned by the
        ``get_scaling_group_state`` function.  Record the number of servers
        received in ``n_servers`` attribute, and the number killed (which
        should be roughly half) in ``n_killed``.
        """

        if code != 200:
            raise Exception("Got 404; where'd the scaling group go?")
        ids = map(lambda obj: obj['id'], response['group']['active'])
        self.n_servers = len(ids)
        self.n_killed = self.n_servers / 2
        return ids[:self.n_killed]

    def _choose_random_servers(self, (code, response), n):
        """Selects ``n`` randomly selected servers from those returned by the
        ``get_scaling_group_state`` function.
        """

        if code != 200:
            raise Exception("Got 404; dude, where's my scaling group?")
        ids = map(lambda obj: obj['id'], response['group']['active'])
        self.n_servers = len(ids)
        self.n_killed = n
        return random.sample(ids, n)

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

    def _wait_for_autoscale_to_catch_up(
        self, _, rcs, timeout=60, period=1, delta=1
    ):
        """Wait for the converger to recognize the reality of this tenant's
        situation and reflect it in the scaling group state accordingly.

        Most tests are organized to execute a scale-up policy with a +1 delta.
        For this reason, if you don't specify a ``delta`` kwArg, it defaults to
        1.  For those tests which have a different scale-up policy, you'll need
        to specify the delta you use explicitly.
        """

        def check((code, response)):
            if code != 200:
                raise BreakLoopException(
                    "Scaling group appears to have disappeared"
                )

            n_remaining = self.n_servers - self.n_killed + delta
            if len(response["group"]["active"]) == n_remaining:
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
