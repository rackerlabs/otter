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
from twisted.python.failure import Failure
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib.autoscale import (
    ScalingGroup,
    ScalingPolicy,
    create_scaling_group_dict,
    extract_active_ids,
)
from otter.integration.lib.cloud_load_balancer import CloudLoadBalancer
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources

from otter.util.http import APIError, check_success, headers


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']
# Get vs dict lookup because it will return None if not found,
# not throw an exception.  None is a valid value for convergence_tenant.
convergence_tenant = os.environ.get('AS_CONVERGENCE_TENANT')


class TestConvergence(unittest.TestCase):
    """This class contains test cases aimed at the Otter Converger."""
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """

        self.pool = HTTPConnectionPool(reactor, False)
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.pool,
            convergence_tenant_override=convergence_tenant,
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

        This variant assumes a scaling group's max_entities field matches that
        for a CLB (as of this writing).
        """
        return self._perform_oobd_clb_test(25)
    test_scaling_to_clb_max_after_oob_delete_type1.timeout = 1800

    def test_scaling_to_clb_max_after_oob_delete_type2(self):
        """This test starts with a scaling group with no servers.  We scale up
        to 24 servers, but after that's done, we delete 2 directly through
        Nova.  After that, we scale up once more by 1 server, thus max'ing out
        the CLB's ports.  We expect that the group will return to 25 servers,
        and does not overshoot in the process.

        Further, we want to make sure the deleted servers are removed from the
        CLB.

        This variant assumes a scaling group's max_entities field exceeds that
        for a CLB (as of this writing).  We use max of CLB + 25.
        """
        return self._perform_oobd_clb_test(50)
    test_scaling_to_clb_max_after_oob_delete_type2.timeout = 1800

    def _perform_oobd_clb_test(self, scaling_group_max_entities):
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
                max_entities=scaling_group_max_entities,
            )

            self.scaling_group = ScalingGroup(
                group_config=scaling_group_body,
                pool=self.pool
            )

            self.first_scaling_policy = ScalingPolicy(
                scale_by=24,
                scaling_group=self.scaling_group
            )

            self.second_scaling_policy = ScalingPolicy(
                scale_by=1,
                scaling_group=self.scaling_group
            )

            return (
                self.scaling_group.start(rcs, self)
                .addCallback(self.first_scaling_policy.start, self)
                .addCallback(self.second_scaling_policy.start, self)
                .addCallback(self.first_scaling_policy.execute)
                .addCallback(
                    self.scaling_group.wait_for_N_servers, 24, timeout=1800
                ).addCallback(self.scaling_group.get_scaling_group_state)
                .addCallback(self._choose_random_servers, 2)
                .addCallback(self._delete_those_servers, rcs)
                .addCallback(self.second_scaling_policy.execute)
                .addCallback(lambda _: self.removed_ids)
                .addCallback(
                    self.scaling_group.wait_for_deleted_id_removal,
                    rcs,
                    total_servers=24,
                ).addCallback(
                    self.scaling_group.wait_for_N_servers, 25, timeout=1800
                )
            )

        return create_clb_first().addCallback(then_test)

    def test_reaction_to_oob_deletion_then_scale_up(self):
        """
        Validate the following edge case:
        - When out of band deletions bring the number of active servers below
          the group min, the servers are replaced in addition to adding the
          requested servers when a policy scales to over the group min.

        Exercise out-of-band server deletion, but then scale up afterwards.
        The goal is to spin up, say, three servers, then use Nova to delete
        one of them directly, without Autoscale's knowledge.  Then we scale up
        by, say, two servers.  If convergence is working as expected, we expect
        five servers at the end.
        """

        rcs = TestResources()

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=3
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.scaling_policy = ScalingPolicy(
            scale_by=2,
            scaling_group=self.scaling_group
        )

        return (
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                    "nova": ("cloudServersOpenStack",),
                },
                region=region
            ).addCallback(self.scaling_group.start, self)
            .addCallback(
                self.scaling_group.wait_for_N_servers, 3, timeout=1800
            ).addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(self._choose_random_servers, 1)
            .addCallback(self._delete_those_servers, rcs)
            .addCallback(self.scaling_policy.start, self)
            .addCallback(self.scaling_policy.execute)
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=3,
            ).addCallback(
                self.scaling_group.wait_for_N_servers, 5, timeout=1800
            )
        )
    test_reaction_to_oob_deletion_then_scale_up.timeout = 1800

    def test_reaction_to_oob_server_deletion(self):
        """
        Validate the following edge case:
        - When out of band deletions bring the number of active servers below
          the group min, the servers are replaced up to the group min when
          convergence is triggered

        Exercise out-of-band server deletion.  The goal is to spin up, say,
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
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                    "nova": ("cloudServersOpenStack",),
                },
                region=region
            ).addCallback(self.scaling_group.start, self)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                N_SERVERS, timeout=1800
            ).addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(self._choose_half_the_servers)
            .addCallback(self._delete_those_servers, rcs)
            # This policy is simply ussed to trigger convergence
            .addCallback(self.scaling_policy.start, self)
            .addCallback(self.scaling_policy.execute)
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=N_SERVERS,
            )
        )
    test_reaction_to_oob_server_deletion.timeout = 1800

    def test_scale_down_after_oobd_non_constrained_z_lessthan_y(self):
        """
        Validate the following edge case:
        - When scaling down after an out of band delete (OOBD) that is
          not constrained by the group max or min, the group stabilizes at a
          number of servers consistent with scaling from the active capacity
          before the OOBD. (i.e. The final result should be as if the OOBD
          never happened.)

            Create a group with min N servers
            Set the group to a desired capacity of x servers
            Delete z (where z<x) of the servers out of band
            Scale down by (y) servers (where z + y < x)
            Validate end state of (x - y) servers for:
                - z < |y|

        """
        rcs = TestResources()

        N = 2
        x = 7
        z = 2
        y = -3

        return self._scale_down_after_oobd_non_constrained_param(
            rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    test_scale_down_after_oobd_non_constrained_z_lessthan_y.timeout = 1800

    def test_scale_down_after_oobd_non_constrained_z_greaterthan_y(self):
        """
        Validate the following edge case:
        - When scaling down after an out of band delete (OOBD) that is
          not constrained by the group max or min, the group stabilizes at a
          number of servers consistent with scaling from the active capacity
          before the OOBD. (i.e. The final result should be as if the OOBD
          never happened.)

            Create a group with min N servers
            Set the group to a desired capacity of x servers
            Delete z (where z<x) of the servers out of band
            Scale down by (y) servers (where z + y < x)
            Validate end state of (x - y) servers for:
                - z > |y|

        """

        rcs = TestResources()

        N = 2
        x = 7
        z = 3
        y = -2

        return self._scale_down_after_oobd_non_constrained_param(
            rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    test_scale_down_after_oobd_non_constrained_z_greaterthan_y.timeout = 1800

    def test_scale_down_after_oobd_non_constrained_z_equal_y(self):
        """
        Validate the following edge case:
        - When scaling down after an out of band delete (OOBD) that is
          not constrained by the group max or min, the group stabilizes at a
          number of servers consistent with scaling from the active capacity
          before the OOBD. (i.e. The final result should be as if the OOBD
          never happened.)

            Create a group with min N servers
            Set the group to a desired capacity of x servers
            Delete z (where z<x) of the servers out of band
            Scale down by (y) servers (where z + y < x)
            Validate end state of (x - y) servers for:
                - z == |y|

        """
        rcs = TestResources()

        N = 2
        x = 7
        z = 3
        y = -3

        return self._scale_down_after_oobd_non_constrained_param(
            rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    test_scale_down_after_oobd_non_constrained_z_equal_y.timeout = 1800

    def _scale_down_after_oobd_non_constrained_param(
            self, rcs, min_servers=0, max_servers=25, set_to_servers=0,
            oobd_servers=0, scale_servers=1):
        # This only applies if not constrained by max/min
        converged_servers = set_to_servers + scale_servers

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=min_servers, max_entities=max_servers
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.policy_set = ScalingPolicy(
            set_to=set_to_servers,
            scaling_group=self.scaling_group
        )

        self.policy_scale = ScalingPolicy(
            scale_by=scale_servers,
            scaling_group=self.scaling_group
        )
        return (
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                    "nova": ("cloudServersOpenStack",),
                },
                region=region
            ).addCallback(self.scaling_group.start, self)
            .addCallback(self.policy_set.start, self)
            .addCallback(self.policy_set.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                set_to_servers, timeout=1800
            ).addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(self._choose_random_servers, oobd_servers)
            .addCallback(self._delete_those_servers, rcs)
            # The execution of the policy triggers convergence
            .addCallback(self.policy_scale.start, self)
            .addCallback(self.policy_scale.execute)
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=set_to_servers,
            )
            .addCallback(self.scaling_group.wait_for_expected_state, rcs,
                         active=converged_servers, pending=0)
        )

    def test_scale_up_after_oobd_at_group_max(self):
        """
        Validate the following edge case:
        - Scaling up when already at the max returns a 403 even after an out
          of band delete (OOBD) has reduced the number of servers below the
          group max. Even though the policy cannot execute, convergence is
          triggered and the deleted servers are replaced.

            Create a group and set the group a capacity of max_servers
            Delete z of the servers out of band
            Attempt to scale up by (y) servers
            Validate end state max_servers
        """
        rcs = TestResources()

        max_servers = 10
        x = max_servers
        z = 2
        y = 5

        return self._scale_down_after_oobd_hitting_constraints(
            rcs, set_to_servers=x, oobd_servers=z, max_servers=max_servers,
            scale_servers=y, converged_servers=max_servers)

    def test_scale_down_past_group_min_after_oobd(self):
        """
        Validate the following edge case:
        - Scaling down when already at the min returns a 403 after an out
          of band delete (OOBD) has reduced the number of servers below the
          group min. Even though the policy cannot execute, convergence is
          triggered and the deleted servers are replaced.

            Create a group with min_servers
            Delete z of the servers out of band
            Attempt to scale down by (y) servers
            Validate end state min_servers
        """
        rcs = TestResources()

        min_servers = 5
        z = 2
        y = -2

        return self._scale_down_after_oobd_hitting_constraints(
            rcs, oobd_servers=z, min_servers=min_servers,
            scale_servers=y,
            converged_servers=min_servers)

    def _assert_error_status_code(self, result, code, rcs):
        """
        Validate that the returned value was a failure with the specified
        status code.
        """
        if not isinstance(result, Failure):
            self.fail('Unexpectedly, this succeeded when it was '
                      'expected to fail')
        elif not result.check(APIError):
            self.fail('Received {0} instead of expected APIError'.format(
                      result.type))
        elif result.value.code != code:
            self.fail('Expected status code {0} but received {1}'.format(
                      code, result.value.code))
        else:
            return rcs

    def _scale_down_after_oobd_hitting_constraints(
            self, rcs, min_servers=0, max_servers=25, set_to_servers=None,
            oobd_servers=0, scale_servers=1, converged_servers=0):

        converged_servers = set_to_servers

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=min_servers, max_entities=max_servers
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.pool
        )

        self.policy_scale = ScalingPolicy(
            scale_by=scale_servers,
            scaling_group=self.scaling_group
        )
        d = self.identity.authenticate_user(
            rcs,
            resources={
                "otter": ("autoscale", "http://localhost:9000/v1.0/{0}"),
                "nova": ("cloudServersOpenStack",),
            },
            region=region
        ).addCallback(self.scaling_group.start, self)

        if set_to_servers is not None:
            self.policy_set = ScalingPolicy(
                set_to=set_to_servers,
                scaling_group=self.scaling_group
            )
            (d.addCallback(self.policy_set.start, self)
             .addCallback(self.policy_set.execute))

        (d.addCallback(
            self.scaling_group.wait_for_N_servers,
            min_servers if set_to_servers is None else set_to_servers,
            timeout=120)
         .addCallback(self.scaling_group.get_scaling_group_state)
         .addCallback(self._choose_random_servers, oobd_servers)
         .addCallback(self._delete_those_servers, rcs)
         # The execution of the policy triggers convergence
         .addCallback(self.policy_scale.start, self)
          .addCallback(self.policy_scale.execute)
         .addBoth(self._assert_error_status_code, 403, rcs)
         # Need to add a check for the expected 403
         .addCallback(lambda _: self.removed_ids)
         .addCallback(
            self.scaling_group.wait_for_deleted_id_removal,
            rcs,
            total_servers=set_to_servers,)
         .addCallback(self.scaling_group.wait_for_expected_state, rcs,
                      active=converged_servers, pending=0))

        return d

    def _choose_half_the_servers(self, (code, response)):
        """Select the first half of the servers returned by the
        ``get_scaling_group_state`` function.  Record the number of servers
        received in ``n_servers`` attribute, and the number killed (which
        should be roughly half) in ``n_killed``.
        """

        if code == 404:
            raise Exception("Got 404; where'd the scaling group go?")
        ids = extract_active_ids(response)
        self.n_servers = len(ids)
        self.n_killed = self.n_servers / 2
        return ids[:self.n_killed]

    def _choose_random_servers(self, state, n):
        """Selects ``n`` randomly selected servers from those returned by the
        ``get_scaling_group_state`` function.
        """
        code, response = state
        if code == 404:
            raise Exception("Got 404; dude, where's my scaling group?")
        ids = extract_active_ids(response)
        self.n_servers = len(ids)
        self.n_killed = n
        return random.sample(ids, n)

    def _delete_those_servers(self, ids, rcs):
        """
        Delete each of the servers selected, and save a list of the
        ids of the deleted servers."""

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
        self.removed_ids = ids
        # If no error occurs while deleting, all the results will be the
        # same.  So just return the 1st, which is just our rcs value.
        return gatherResults(deferreds).addCallback(lambda rslts: rslts[0])
