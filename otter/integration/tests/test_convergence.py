"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

from __future__ import print_function

import os
from functools import wraps

from twisted.internet import reactor
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib.autoscale import (
    ScalingGroup,
    ScalingPolicy,
    create_scaling_group_dict,
    extract_active_ids,
)
from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer, ExcludesAllIPs)
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.nova import NovaServer, delete_servers
from otter.integration.lib.resources import TestResources


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']
# Get vs dict lookup because it will return None if not found,
# not throw an exception.  None is a valid value for convergence_tenant.
convergence_tenant = os.environ.get('AS_CONVERGENCE_TENANT')
otter_key = os.environ.get('AS_AUTOSCALE_SC_KEY', 'autoscale')
otter_url = os.environ.get('AS_AUTOSCALE_LOCAL_URL')
nova_key = os.environ.get('AS_NOVA_SC_KEY', 'cloudServersOpenStack')
clb_key = os.environ.get('AS_CLB_SC_KEY', 'cloudLoadBalancers')


class TestHelper(object):
    """
    A helper class that contains useful functions for actual test cases.
    """
    def __init__(self, test_case):
        """
        Set up the test case, HTTP pool, identity, and cleanup.
        """
        self.test_case = test_case

        self.pool = HTTPConnectionPool(reactor, False)
        self.test_case.addCleanup(self.pool.closeCachedConnections)

    def oob_delete_then(self, rcs, scaling_group, num, clbs=None):
        """
        Return a decorator that wraps a function call with logic to out-of-band
        delete (not disown) some number of servers, and verifies that the
        servers are deleted and cleaned up.
        """
        def decorated(function):
            @wraps(function)
            @inlineCallbacks
            def wrapper(*args, **kwargs):
                chosen = yield scaling_group.choose_random_servers(rcs, num)

                # get ips for chosen servers if CLBs are provided, becase we
                # will need to verify that the CLBs are cleaned up.
                if clbs is not None:
                    ips = yield scaling_group.get_servicenet_ips(rcs, chosen)

                yield delete_servers(chosen, rcs, pool=self.pool)
                yield function(*args, **kwargs)

                checks = [
                    scaling_group.wait_for_deleted_id_removal(chosen, rcs)]

                if clbs is not None:
                    checks += [
                        clb.wait_for_nodes(rcs, ExcludesAllIPs(ips.values()),
                                           timeout=1800)
                        for clb in clbs]

                yield gatherResults(checks)
                returnValue(rcs)

            return wrapper
        return decorated


class TestConvergence(unittest.TestCase):
    """This class contains test cases aimed at the Otter Converger."""
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self)
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.helper.pool,
            convergence_tenant_override=convergence_tenant,
        )

    def test_scale_over_group_max_after_metadata_removal_reduced_grp_max(self):
        """
        CATC-017-a

        Attempt to scale over the group max, but only after metadata removal on
        some random sampling of servers.  Note that this version exercises the
        path that group max is less than CLB max.
        """

        rcs = TestResources()

        self.untouchable_scaling_group = ScalingGroup(
            group_config=create_scaling_group_dict(
                image_ref=image_ref, flavor_ref=flavor_ref, min_entities=4,
            ),
            pool=self.helper.pool
        )

        self.scaling_group = ScalingGroup(
            group_config=create_scaling_group_dict(
                image_ref=image_ref, flavor_ref=flavor_ref, max_entities=12,
            ),
            pool=self.helper.pool
        )

        self.scale_up_to_max = ScalingPolicy(
            scale_by=12,
            scaling_group=self.scaling_group
        )

        self.scale_beyond_max = ScalingPolicy(
            scale_by=5,
            scaling_group=self.scaling_group
        )

        def check_state(state, then=None):
            code, response = state
            if code == 404:
                raise Exception("Enterprise to Scaling Group, please respond.")
            if then:
                return then(response)

        def keep_state(response):
            self.untouchable_group_ids = extract_active_ids(response)
            return rcs

        def double_check_state(response):
            latest_ids = extract_active_ids(response)
            if not all(i in self.untouchable_group_ids for i in latest_ids):
                raise Exception("Untouchable group mutilated somehow.")
            return rcs

        return (
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": (otter_key, otter_url),
                    "nova": (nova_key,),
                },
                region=region,
            ).addCallback(self.scaling_group.start, self)
            .addCallback(self.untouchable_scaling_group.start, self)
            .addCallback(
                self.untouchable_scaling_group.wait_for_N_servers, 4,
                timeout=1800
            ).addCallback(
                self.untouchable_scaling_group.get_scaling_group_state
            ).addCallback(check_state, then=keep_state)
            .addCallback(self.scale_up_to_max.start, self)
            .addCallback(self.scale_beyond_max.start, self)
            .addCallback(self.scale_up_to_max.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers, 12, timeout=1800
            ).addCallback(self.scaling_group.choose_random_servers, 3)
            .addCallback(self._remove_metadata, rcs)
            .addCallback(lambda _: rcs)
            .addCallback(self.scale_beyond_max.execute, success_codes=[403])
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=12,
            ).addCallback(
                self.scaling_group.wait_for_N_servers, 12, timeout=1800
            ).addCallback(
                self.untouchable_scaling_group.get_scaling_group_state
            ).addCallback(check_state, then=double_check_state)
        )

    def test_scale_over_group_max_after_metadata_removal(self):
        """
        CATC-018-a

        Attempt to scale over the group max, but only after metadata removal on
        some random sampling of servers.
        """

        rcs = TestResources()

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
        )

        self.scale_up_to_max = ScalingPolicy(
            scale_by=25,
            scaling_group=self.scaling_group
        )

        self.scale_beyond_max = ScalingPolicy(
            scale_by=5,
            scaling_group=self.scaling_group
        )

        return (
            self.identity.authenticate_user(
                rcs,
                resources={
                    "otter": (otter_key, otter_url),
                    "nova": (nova_key,),
                },
                region=region,
            ).addCallback(self.scaling_group.start, self)
            .addCallback(self.scale_up_to_max.start, self)
            .addCallback(self.scale_beyond_max.start, self)
            .addCallback(self.scale_up_to_max.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers, 25, timeout=1800
            ).addCallback(self.scaling_group.choose_random_servers, 3)
            .addCallback(self._remove_metadata, rcs)
            .addCallback(lambda _: rcs)
            .addCallback(self.scale_beyond_max.execute, success_codes=[403])
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=25,
            ).addCallback(
                self.scaling_group.wait_for_N_servers, 25, timeout=1800
            )
        )

    def test_scaling_to_clb_max_after_oob_delete_type1(self):
        """
        CATC-015-a

        This test starts with a scaling group with no servers.  We scale up
        to 24 servers, but after that's done, we delete 2 directly through
        Nova.  After that, we scale up once more by 1 server, thus max'ing out
        the CLB's ports.  We expect that the group will return to 25 servers,
        and does not overshoot or enter error state in the process.

        Further, we want to make sure the deleted servers are removed from the
        CLB.

        This variant assumes a scaling group's max_entities field matches that
        for a CLB (as of this writing).
        """
        return self._perform_oobd_clb_test(25)

    def test_scaling_to_clb_max_after_oob_delete_type2(self):
        """
        CATC-015-b

        This test starts with a scaling group with no servers.  We scale up
        to 24 servers, but after that's done, we delete 2 directly through
        Nova.  After that, we scale up once more by 1 server, thus max'ing out
        the CLB's ports.  We expect that the group will return to 25 servers,
        and does not overshoot or error in the process.

        Further, we want to make sure the deleted servers are removed from the
        CLB.

        This variant assumes a scaling group's max_entities field exceeds that
        for a CLB (as of this writing).  We use max of CLB + 10.
        """
        return self._perform_oobd_clb_test(35)

    def _perform_oobd_clb_test(self, scaling_group_max_entities):
        rcs = TestResources()

        def create_clb_first():
            self.clb = CloudLoadBalancer(pool=self.helper.pool)
            return (
                self.identity.authenticate_user(
                    rcs,
                    resources={
                        "otter": (otter_key, otter_url),
                        "nova": (nova_key,),
                        "loadbalancers": (clb_key,)
                    },
                    region=region,
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
                pool=self.helper.pool
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
                ).addCallback(self.scaling_group.choose_random_servers, 2)
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

    def _delete_those_servers(self, ids, rcs):
        """
        Delete each of the servers selected, and save a list of the
        ids of the deleted servers."""
        self.removed_ids = ids
        return (
            delete_servers(ids, rcs, pool=self.helper.pool)
            .addCallback(lambda rslts: rcs)
        )

    def _remove_metadata(self, ids, rcs):
        """Given a list of server IDs, use Nova to remove their metadata.
        This will strip them of their association with Autoscale.
        """
        self.removed_ids = ids
        return gatherResults([
            NovaServer(id=_id, pool=self.helper.pool).update_metadata({}, rcs)
            for _id in ids]).addCallback(lambda _: rcs)


class ConvergenceSet1(unittest.TestCase):
    """
    Class for CATC 4-12 that run without CLB, but can be run with CLB (
    so the CLB versions of these tests can be run by just subclassing this
    test case)
    """
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self)
        self.clbs = []
        self.rcs = TestResources()
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.helper.pool,
            convergence_tenant_override=convergence_tenant,
        )
        return self.identity.authenticate_user(
            self.rcs,
            resources={
                "otter": (otter_key, otter_url),
                "nova": (nova_key,),
            },
            region=region
        )

    def use_clb_arg(self):
        """
        Get the CLB arguments with which to create a scaling group, if
        ``clbs`` is set on the test case.
        """
        if self.clbs is not None:
            return [clb.scaling_group_spec() for clb in self.clbs]
        return None

    def test_reaction_to_oob_server_deletion_below_min(self):
        """
        CATC-004-a

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

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=N_SERVERS, use_lbs=self.use_clb_arg()
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
        )

        return (
            self.scaling_group.start(self.rcs, self)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                N_SERVERS, timeout=1800
            )
            .addCallback(self.helper.oob_delete_then(
                self.rcs, self.scaling_group, N_SERVERS / 2)(
                self.scaling_group.trigger_convergence))
        )

    def test_reaction_to_oob_deletion_then_scale_up(self):
        """
        CATC-005-a

        CLB_NEEDED

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
        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=3, use_lbs=self.use_clb_arg()
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
        )

        self.scaling_policy = ScalingPolicy(
            scale_by=2,
            scaling_group=self.scaling_group
        )

        return (
            self.scaling_group.start(self.rcs, self)
            .addCallback(self.scaling_policy.start, self)
            .addCallback(
                self.scaling_group.wait_for_N_servers, 3, timeout=1800)
            .addCallback(self.helper.oob_delete_then(
                self.rcs, self.scaling_group, 1)(self.scaling_policy.execute))
            .addCallback(
                self.scaling_group.wait_for_N_servers, 5, timeout=1800
            )
        )

    def test_scale_down_after_oobd_non_constrained_z_lessthan_y(self):
        """
        CATC-006-a

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
        N = 2
        x = 7
        z = 2
        y = -3

        return self._scale_down_after_oobd_non_constrained_param(
            self.rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    def test_scale_down_after_oobd_non_constrained_z_greaterthan_y(self):
        """
        CATC-006-b

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
        N = 2
        x = 7
        z = 3
        y = -2

        return self._scale_down_after_oobd_non_constrained_param(
            self.rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    def test_scale_down_after_oobd_non_constrained_z_equal_y(self):
        """
        CATC-006-c

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
        N = 2
        x = 7
        z = 3
        y = -3

        return self._scale_down_after_oobd_non_constrained_param(
            self.rcs, min_servers=N, set_to_servers=x, oobd_servers=z,
            scale_servers=y)

    def _scale_down_after_oobd_non_constrained_param(
            self, rcs, min_servers=0, max_servers=25, set_to_servers=0,
            oobd_servers=0, scale_servers=1):
        """
        Helper for CATC-006
        """
        # This only applies if not constrained by max/min
        converged_servers = set_to_servers + scale_servers

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=min_servers, max_entities=max_servers,
            use_lbs=self.use_clb_arg()
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
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
            self.scaling_group.start(rcs, self)
            .addCallback(self.policy_set.start, self)
            .addCallback(self.policy_scale.start, self)
            .addCallback(self.policy_set.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                set_to_servers, timeout=1800)
            .addCallback(self.helper.oob_delete_then(
                rcs, self.scaling_group, oobd_servers)(
                self.policy_scale.execute))
            .addCallback(self.scaling_group.wait_for_expected_state, rcs,
                         timeout=1800, active=converged_servers, pending=0)
        )

    def test_scale_up_after_oobd_at_group_max(self):
        """
        CATC-007-a

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
        max_servers = 10
        x = max_servers
        z = 2
        y = 5

        return self._scale_down_after_oobd_hitting_constraints(
            self.rcs, set_to_servers=x, oobd_servers=z,
            max_servers=max_servers, scale_servers=y,
            converged_servers=max_servers)

    def test_scale_down_past_group_min_after_oobd(self):
        """
        CATC-007-b

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
        min_servers = 5
        z = 2
        y = -2

        return self._scale_down_after_oobd_hitting_constraints(
            self.rcs, oobd_servers=z, min_servers=min_servers,
            scale_servers=y,
            converged_servers=min_servers)

    def test_group_config_update_triggers_convergence(self):
        """
        CATC-008-a

        Validate the following edge case:
        - On a group that has experienced and out of band delete,
          when the group configuration is updated convergence is triggered
        """
        set_to_servers = 5
        max_servers = 10

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            max_entities=max_servers, use_lbs=self.use_clb_arg()
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
        )

        self.policy_set = ScalingPolicy(
            set_to=set_to_servers,
            scaling_group=self.scaling_group
        )

        return (
            self.scaling_group.start(self.rcs, self)
            .addCallback(self.policy_set.start, self)
            .addCallback(self.policy_set.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                set_to_servers, timeout=1800
            )
            .addCallback(
                self.helper.oob_delete_then(
                    self.rcs, self.scaling_group, set_to_servers / 2)(
                    self.scaling_group.update_group_config),
                maxEntities=max_servers + 2)
        )

    def _scale_down_after_oobd_hitting_constraints(
            self, rcs, min_servers=0, max_servers=25, set_to_servers=None,
            oobd_servers=0, scale_servers=1, converged_servers=0):

        converged_servers = set_to_servers

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=min_servers, max_entities=max_servers,
            use_lbs=self.use_clb_arg()
        )

        self.scaling_group = ScalingGroup(
            group_config=scaling_group_body,
            pool=self.helper.pool
        )

        self.policy_scale = ScalingPolicy(
            scale_by=scale_servers,
            scaling_group=self.scaling_group
        )

        d = self.scaling_group.start(rcs, self)

        if set_to_servers is not None:
            self.policy_set = ScalingPolicy(
                set_to=set_to_servers,
                scaling_group=self.scaling_group
            )

            (d.addCallback(self.policy_set.start, self)
             .addCallback(self.policy_set.execute))

        def fail_to_execute_over_max(_):
            # Execute a scaling policy, which should return 403 because it
            # would bring the desired over the max.  But convergence is
            # triggered
            return self.policy_scale.start(rcs, self).addCallback(
                self.policy_scale.execute, success_codes=[403])

        (d.addCallback(
            self.scaling_group.wait_for_N_servers,
            min_servers if set_to_servers is None else set_to_servers,
            timeout=120)
         .addCallback(self.helper.oob_delete_then(
             rcs, self.scaling_group, oobd_servers)(
             fail_to_execute_over_max))
         .addCallback(self.scaling_group.wait_for_expected_state, rcs,
                      timeout=1800, active=converged_servers, pending=0))

        return d


class ConvergenceSet1WithCLB(ConvergenceSet1):
    """
    Class for CATC 4-12 that run with CLB.
    """
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self)
        self.clbs = [CloudLoadBalancer(pool=self.helper.pool)]
        self.rcs = TestResources()
        self.identity = IdentityV2(
            auth=auth, username=username, password=password,
            endpoint=endpoint, pool=self.helper.pool,
            convergence_tenant_override=convergence_tenant,
        )
        return self.identity.authenticate_user(
            self.rcs,
            resources={
                "otter": (otter_key, otter_url),
                "nova": (nova_key,),
                "loadbalancers": (clb_key,)
            },
            region=region
        ).addCallback(lambda _: gatherResults([
            clb.start(self.rcs, self)
            .addCallback(clb.wait_for_state, "ACTIVE", 600)
            for clb in self.clbs])
        )
