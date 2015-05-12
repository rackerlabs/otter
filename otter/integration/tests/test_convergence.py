"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

from __future__ import print_function

import os
from functools import wraps

from testtools.matchers import ContainsDict, Equals, MatchesAll

from twisted.internet import reactor
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.trial import unittest
from twisted.web.client import HTTPConnectionPool

from otter import auth
from otter.integration.lib.autoscale import (
    ExcludesServers,
    HasActive,
    ScalingGroup,
    ScalingPolicy,
    create_scaling_group_dict,
    extract_active_ids,
)
from otter.integration.lib.cloud_load_balancer import (
    CloudLoadBalancer, ContainsAllIPs, ExcludesAllIPs, HasLength)
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.mimic import MimicNova
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

# these are the service names for mimic control planes
mimic_nova_key = os.environ.get("MIMICNOVA_SC_KEY", 'cloudServersBehavior')


class TestHelper(object):
    """
    A helper class that contains useful functions for actual test cases.  This
    also creates a number of CLB that are required.
    """
    def __init__(self, test_case, num_clbs=0):
        """
        Set up the test case, HTTP pool, identity, and cleanup.
        """
        self.test_case = test_case
        self.pool = HTTPConnectionPool(reactor, False)
        self.test_case.addCleanup(self.pool.closeCachedConnections)

        self.clbs = [CloudLoadBalancer(pool=self.pool)
                     for _ in range(num_clbs)]

    def create_group(self, **kwargs):
        """
        Return a scaling group with the helper's pool.
        """
        if self.clbs:
            kwargs['use_lbs'] = [clb.scaling_group_spec() for clb in self.clbs]

        return ScalingGroup(
            group_config=create_scaling_group_dict(**kwargs),
            pool=self.pool)

    @inlineCallbacks
    def start_group_and_wait(self, group, rcs, desired=None):
        """
        Start a group, and if desired is supplied, creates and executes a
        policy that scales to that number.  This would be used for example
        if we wanted to scale to the max of a group, but did not want the min
        to be equal to the max.

        This also waits for the desired number of servers to be reached - that
        would be desired if provided, or the min if not provided.

        :param TestResources rcs: An instance of
            :class:`otter.integration.lib.resources.TestResources`
        :param ScalingGroup group: An instance of
            :class:`otter.integration.lib.autoscale.ScalingGroup` to start -
            this group should not have been started already.
        :param int desired: A desired number to scale to.
        """
        yield group.start(rcs, self.test_case)
        if desired is not None:
            p = ScalingPolicy(set_to=desired, scaling_group=group)
            yield p.start(rcs, self.test_case)
            yield p.execute(rcs)

        if desired is None:
            desired = group.group_config['groupConfiguration'].get(
                'minEntities', 0)

        yield group.wait_for_state(
            rcs,
            MatchesAll(HasActive(desired),
                       ContainsDict({'pendingCapacity': Equals(0),
                                     'desiredCapacity': Equals(desired)})),
            timeout=600)

        if self.clbs:
            ips = yield group.get_servicenet_ips(rcs)
            yield gatherResults([
                clb.wait_for_nodes(
                    rcs, ContainsAllIPs(ips.values()), timeout=600)
                for clb in self.clbs])

        returnValue(rcs)

    def oob_delete_then(self, rcs, scaling_group, num):
        """
        Return a decorator that wraps a function call with logic to out-of-band
        delete (not disown) some number of servers, and verifies that the
        servers are deleted and cleaned up from CLBs.

        :param TestResources rcs: An instance of
            :class:`otter.integration.lib.resources.TestResources`
        :param ScalingGroup group: An instance of
            :class:`otter.integration.lib.autoscale.ScalingGroup` to start -
            this group should have been started already.
        :param int num: The number of servers to delete out of band.
        """
        def decorated(function):
            @wraps(function)
            @inlineCallbacks
            def wrapper(*args, **kwargs):
                chosen = yield scaling_group.choose_random_servers(rcs, num)

                # Get ips for chosen servers if CLBs are provided, because we
                # will need to verify that the CLBs are cleaned up.  Assume
                # that it's been verified that the nodes are already on the
                # CLB.
                if self.clbs is not None:
                    ips = yield scaling_group.get_servicenet_ips(rcs, chosen)

                yield delete_servers(chosen, rcs, pool=self.pool)
                yield function(*args, **kwargs)

                checks = [
                    scaling_group.wait_for_state(rcs, ExcludesServers(chosen))]

                if self.clbs is not None:
                    checks += [
                        clb.wait_for_nodes(rcs, ExcludesAllIPs(ips.values()),
                                           timeout=600)
                        for clb in self.clbs]

                yield gatherResults(checks)
                returnValue(rcs)

            return wrapper
        return decorated


def tag(*tags):
    """
    Decorator that adds tags to a function by setting the property "tags".

    This should be added upstream to Twisted trial.
    """
    def decorate(function):
        function.tags = tags
        return function
    return decorate


def skip_me(reason):
    """
    Decorator that skips a test method or test class by setting the property
    "skip".  This decorator is not named "skip", because setting "skip" on a
    module skips the whole tes module.

    This should be added upstream to Twisted trial.
    """
    def decorate(function):
        function.skip = reason
        return function
    return decorate


def copy_test_methods(from_class, to_class, filter_and_change=None):
    """
    Copy test methods (methods that start with `test_*`) from ``from_class`` to
    ``to_class``.  If a decorator is provided, the test method on the
    ``to_class`` will first be decorated before being set.

    :param class from_class: The test case to copy from
    :param class to_class: The test case to copy to
    :param callable filter_and_change: A function that takes a test name
        and test method, and returns a tuple of `(name, method)`
        if the test method should be copied. None else.  This allows the
        method name to change, the method to be decorated and/or skipped.
    """
    for name, attr in from_class.__dict__.items():
        if name.startswith('test_') and callable(attr):
            if filter_and_change is not None:
                filtered = filter_and_change(name, attr)
                if filtered is not None:
                    setattr(to_class, *filtered)
            else:
                setattr(to_class, name, attr)


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
                self.untouchable_scaling_group.wait_for_state, HasActive(4),
                timeout=1800
            ).addCallback(
                self.untouchable_scaling_group.get_scaling_group_state
            ).addCallback(check_state, then=keep_state)
            .addCallback(self.scale_up_to_max.start, self)
            .addCallback(self.scale_beyond_max.start, self)
            .addCallback(self.scale_up_to_max.execute)
            .addCallback(
                self.scaling_group.wait_for_state, HasActive(12), timeout=1800
            ).addCallback(self.scaling_group.choose_random_servers, 3)
            .addCallback(self._remove_metadata, rcs)
            .addCallback(lambda _: rcs)
            .addCallback(self.scale_beyond_max.execute, success_codes=[403])
            .addCallback(
                lambda _: self.scaling_group.wait_for_state(
                    rcs, MatchesAll(
                        ExcludesServers(self.removed_ids),
                        HasActive(12)),
                    timeout=1800)
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
                self.scaling_group.wait_for_state, HasActive(25), timeout=1800
            ).addCallback(self.scaling_group.choose_random_servers, 3)
            .addCallback(self._remove_metadata, rcs)
            .addCallback(lambda _: rcs)
            .addCallback(self.scale_beyond_max.execute, success_codes=[403])
            .addCallback(lambda _: self.scaling_group.wait_for_state(
                rcs, MatchesAll(
                    ExcludesServers(self.removed_ids),
                    HasActive(25)),
                timeout=1800)
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
                    self.scaling_group.wait_for_state, HasActive(24),
                    timeout=1800)
                .addCallback(self.helper.oob_delete_then(
                    rcs, self.scaling_group, 2)(
                    self.second_scaling_policy.execute))
                .addCallback(lambda _: self.scaling_group.wait_for_state(
                    rcs, HasActive(25), timeout=1800)
                )
            )

        return create_clb_first().addCallback(then_test)

    def _remove_metadata(self, ids, rcs):
        """Given a list of server IDs, use Nova to remove their metadata.
        This will strip them of their association with Autoscale.
        """
        self.removed_ids = ids
        return gatherResults([
            NovaServer(id=_id, pool=self.helper.pool).update_metadata({}, rcs)
            for _id in ids]).addCallback(lambda _: rcs)


def _test_scaling_after_oobd(
        helper, rcs, min_servers=0, max_servers=25,
        set_to_servers=None, oobd_servers=0, scale_servers=1,
        converged_servers=0, scale_should_fail=False):
    """
    Helper function that creates a scaling group and sets the desired capacity
    to a certain number.  Then OOB-deletes some number of servers and scales.
    Then it waits for some number of servers to be active.
    """
    scaling_group = helper.create_group(
        image_ref=image_ref, flavor_ref=flavor_ref,
        min_entities=min_servers, max_entities=max_servers
    )

    policy_scale = ScalingPolicy(
        scale_by=scale_servers,
        scaling_group=scaling_group
    )

    return (
        helper.start_group_and_wait(scaling_group, rcs,
                                    desired=set_to_servers)
        .addCallback(policy_scale.start, helper.test_case)
        .addCallback(
            helper.oob_delete_then(
                rcs, scaling_group, oobd_servers)(policy_scale.execute),
            success_codes=(
                [403] if scale_should_fail else [202]))
        .addCallback(lambda _: scaling_group.wait_for_state(
            rcs, MatchesAll(
                HasActive(converged_servers),
                ContainsDict({
                    'pendingCapacity': Equals(0),
                    'desiredCapacity': Equals(converged_servers)
                })
            ), timeout=600)
        )
        .addCallback(lambda _: scaling_group)
    )


@inlineCallbacks
def _test_error_active_and_converge(
        helper, rcs, num_to_error, scale_by=0,
        min_servers=0, max_servers=25, desired_servers=None):
    """
    Helper function that creates a scaling group and sets the desired capacity
    to a certain number.  It waits for those servers to become active.  Once
    active, uses Mimic to error those servers.

    It then either scales up or down (or just triggers convergence, based on
    the scale_by number), and waits for the final number of servers to
    stabilize and for the errored servers to be deleted.
    """
    scaling_group = helper.create_group(
        image_ref=image_ref, flavor_ref=flavor_ref,
        min_entities=min_servers, max_entities=max_servers
    )

    yield helper.start_group_and_wait(scaling_group, rcs,
                                      desired=desired_servers)

    to_error = yield scaling_group.choose_random_servers(rcs, num_to_error)

    ips = {}
    if helper.clbs:
        ips = yield scaling_group.get_servicenet_ips(rcs, to_error)

    # cause mimic to error the chosen servers
    yield MimicNova(pool=helper.pool).change_server_statuses(
        rcs, {server_id: "ERROR" for server_id in to_error})

    if scale_by == 0:
        yield scaling_group.trigger_convergence(rcs)
    else:
        p = ScalingPolicy(scale_by=scale_by, scaling_group=scaling_group)
        yield p.start(rcs, helper.test_case)
        yield p.execute(rcs)

    if desired_servers is None:
        desired_servers = min_servers

    end_state = [scaling_group.wait_for_state(
        rcs,
        MatchesAll(
            HasActive(desired_servers + scale_by),
            ContainsDict({
                'pendingCapacity': Equals(0),
                'desiredCapacity': Equals(desired_servers + scale_by)
            }),
            ExcludesServers(to_error)
        ),
        timeout=600
    )]

    if helper.clbs:
        end_state += [clb.wait_for_nodes(rcs, ExcludesAllIPs(ips.values()),
                                         timeout=600)
                      for clb in helper.clbs]

    yield gatherResults(end_state)
    returnValue(scaling_group)


class ConvergenceSet1(unittest.TestCase):
    """
    Class for CATC 4-12 that run without CLB, but can be run with CLB (
    so the CLB versions of these tests can be run by just subclassing this
    test case).
    """
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self)
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
                "mimic_nova": (mimic_nova_key,)
            },
            region=region
        )

    @tag("CATC-004")
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

        self.scaling_group = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=N_SERVERS)

        return (
            self.helper.start_group_and_wait(self.scaling_group, self.rcs)
            .addCallback(self.helper.oob_delete_then(
                self.rcs, self.scaling_group, N_SERVERS / 2)(
                self.scaling_group.trigger_convergence))
        )

    @tag("CATC-005")
    def test_reaction_to_oob_deletion_then_scale_up(self):
        """
        CATC-005-a

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
        return _test_scaling_after_oobd(
            self.helper, self.rcs, min_servers=3, oobd_servers=1,
            scale_servers=2, converged_servers=5)

    @tag("CATC-006")
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

        return _test_scaling_after_oobd(
            self.helper, self.rcs, min_servers=N, set_to_servers=x,
            oobd_servers=z, scale_servers=y, converged_servers=(x + y))

    @tag("CATC-006")
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

        return _test_scaling_after_oobd(
            self.helper, self.rcs, min_servers=N, set_to_servers=x,
            oobd_servers=z, scale_servers=y, converged_servers=(x + y))

    @tag("CATC-006")
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

        return _test_scaling_after_oobd(
            self.helper, self.rcs, min_servers=N, set_to_servers=x,
            oobd_servers=z, scale_servers=y, converged_servers=(x + y))

    @tag("CATC-007")
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

        return _test_scaling_after_oobd(
            self.helper, self.rcs, set_to_servers=x, oobd_servers=z,
            max_servers=max_servers, scale_servers=y,
            converged_servers=max_servers, scale_should_fail=True)

    @tag("CATC-007")
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

        return _test_scaling_after_oobd(
            self.helper, self.rcs, oobd_servers=z, min_servers=min_servers,
            scale_servers=y, converged_servers=min_servers,
            scale_should_fail=True)

    @tag("CATC-008")
    def test_group_config_update_triggers_convergence(self):
        """
        CATC-008-a

        Validate the following edge case:
        - On a group that has experienced and out of band delete,
          when the group configuration is updated convergence is triggered
        """
        set_to_servers = 5
        max_servers = 10

        self.scaling_group = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref,
            max_entities=max_servers
        )

        return (
            self.helper.start_group_and_wait(self.scaling_group,
                                             self.rcs,
                                             desired=set_to_servers)
            .addCallback(
                self.helper.oob_delete_then(
                    self.rcs, self.scaling_group, set_to_servers / 2)(
                    self.scaling_group.update_group_config),
                maxEntities=max_servers + 2)
        )

    @tag("CATC-011")
    def test_scale_up_after_servers_error_from_active(self):
        """
        CATC-011

        Requires Mimic for error injection.

        1. Create a scaling group with N min servers and M max servers.
        2. After the servers are active, E go into error state.
        3. Scale up by (N-M).
        4. Assert that there should be M active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _test_error_active_and_converge(
            self.helper, self.rcs, num_to_error=1, scale_by=2,
            min_servers=2, max_servers=4)

    @tag("CATC-012")
    def test_scale_down_after_servers_error_from_active(self):
        """
        CATC-012

        Requires Mimic for error injection.

        1. Create a scaling group with N min servers and M max servers.
        2. Set the number of servers to be X (N<X<M)
        2. After the servers are active, E go into error state (E>(X-N))
        3. Scale down to N servers on the group.
        4. Assert that there should be N active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _test_error_active_and_converge(
            self.helper, self.rcs, num_to_error=2, scale_by=-1,
            min_servers=2, max_servers=4, desired_servers=3)

    @tag("CATC-013")
    def test_trigger_convergence_after_servers_error_from_active(self):
        """
        CATC-013

        Requires Mimic for error injection.

        1. Create a scaling group with N min servers and M max servers.
        2. Set the number of servers to be X (N<X<M)
        2. After the servers are active, E go into error state (E<(X-N))
        3. Trigger a convergence cycle.
        4. Assert that there should be X active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _test_error_active_and_converge(
            self.helper, self.rcs, num_to_error=2, scale_by=0,
            min_servers=2, max_servers=4, desired_servers=3)


def _catc_tags(start_num, end_num):
    """
    Return a list of CATC tags corresponding to the start test number and end
    test number.  For example, start=1 and end=3 would return:
    ["CATC-001", "CATC-002", "CATC-003"].
    """
    return ["CATC-0{0:02d}".format(i) for i in range(start_num, end_num + 1)]


def _delete_a_clb_and_scale(rcs, helper, group, scale_by, delete_clb=None):
    """
    1. Delete the first load balancer using the provided function (it may set
       the load balancer to PENDING_DELETE instead, for example)
    2. Scale.

    :param callable delete_clb: function that takes a test resource
        and a load balancer and deletes (or pending-deletes) the
        load balancer.
    """
    if delete_clb is not None:
        d = delete_clb(helper.clbs[0](rcs))
    else:
        d = helper.clbs[0].delete(rcs, success_codes=[202])

    policy = ScalingPolicy(scale_by=scale_by, scaling_group=group)
    d.addCallback(lambda _: policy.start(rcs, helper.test_case))
    d.addCallback(policy.execute)
    d.addCallback(lambda _: rcs)
    return d


class ConvergenceTestsWith1CLB(unittest.TestCase):
    """
    Tests for convergence that require a single CLB.
    """
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self, num_clbs=1)
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
                "loadbalancers": (clb_key,),
                "mimic_nova": (mimic_nova_key,)
            },
            region=region
        ).addCallback(lambda _: gatherResults([
            clb.start(self.rcs, self)
            .addCallback(clb.wait_for_state, "ACTIVE", 600)
            for clb in self.helper.clbs])
        )

    @classmethod
    def _only_oob_del_and_error_tests(cls, name, method):
        """
        To be used by :func:`copy_test_methods` to filter only certain non-CLB
        tests (the ones testing out of band deletions, servers going into
        error, servers timing out from builds), and ensure that active servers
        on the group, when the test has finished, are all properly on the CLB.

        Note that the methods copied should all return the scaling group, so
        that the group's active servers can be checked against the CLB.

        Also note that this filters out only the tests tagged CATC-004 through
        CATC-013, because those where the numbers in the original test plan
        corresponding to the OOB-delete/error test cases.
        """
        tags = getattr(method, 'tags', ())
        if not any(tag in tags for tag in _catc_tags(4, 13)):
            return None

        @wraps(method)
        @inlineCallbacks
        def wrapper(self, *args, **kwargs):
            scaling_group = yield method(self, *args, **kwargs)

            ips = yield scaling_group.get_servicenet_ips(self.rcs)

            checks = MatchesAll(ContainsAllIPs(ips.values()),
                                HasLength(len(ips)))

            yield gatherResults([
                clb.wait_for_nodes(self.rcs, checks, timeout=1800)
                for clb in self.helper.clbs])

        if any(tag in tags for tag in _catc_tags(4, 8)):
            wrapper.skip = (
                "Autoscale does not clean up servers deleted OOB yet. "
                "See #881.")
        return (name, wrapper)

    @tag("CATC-020")
    def test_delete_all_loadbalancers_and_scale_up(self, delete_clb=None):
        """
        CATC-020-a. This will also tested with starting with 2 load balancers.

        1. Creates a scaling group with a load balancer and 1 server.
        2. Ensure that the server is active and added to the load balancer.
        3. Delete the load balancer using the delete command (it may set
           the load balancer to PENDING_DELETE instead, for example)
        4. Attempt to scale up by 1.
        5. Assert that the scaling group goes into error state, and that the
            server that is now broken is no longer active.

        :param callable delete_clb: function that takes a test resource
            and a load balancer and deletes (or pending-deletes) the
            load balancer.
        """
        group = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref, min_entities=1)

        return (
            self.helper.start_group_and_wait(group, self.rcs)
            .addCallback(_delete_a_clb_and_scale, self.helper, group,
                         scale_by=1, delete_clb=delete_clb)
            .addCallback(
                group.wait_for_state,
                MatchesAll(
                    ContainsDict({
                        'pendingCapacity': Equals(2),
                        'desiredCapacity': Equals(2),
                        'status': Equals("ERROR")
                    }),
                    HasActive(0)),
                timeout=600
            )
        )

    @tag("CATC-020")
    def test_delete_all_loadbalancers_and_scale_down(self, delete_clb=None):
        """
        CATC-020-b.  This will also tested with starting with 2 load balancers.

        1. Creates a scaling group with a load balancer, and scale to 1 server.
        2. Ensure that the servers are active and added to the load balancer.
        3. Delete the load balancer using the delete command (it may set
           the load balancer to PENDING_DELETE instead, for example)
        4. Scale down by 1.
        5. Assert that the scaling group does not go into error state, and that
           the server is successfully deleted.

        :param callable delete_clb: function that takes a test resource
            and a load balancer and deletes (or pending-deletes) the
            load balancer.
        """
        group = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref)

        return (
            self.helper.start_group_and_wait(group, self.rcs, desired=1)
            .addCallback(_delete_a_clb_and_scale, self.helper, group,
                         scale_by=-1, delete_clb=delete_clb)
            .addCallback(
                group.wait_for_state,
                MatchesAll(
                    ContainsDict({
                        'pendingCapacity': Equals(0),
                        'desiredCapacity': Equals(0),
                        'status': Equals("ACTIVE")
                    }),
                    HasActive(0)),
                timeout=600
            )
        )


copy_test_methods(
    ConvergenceSet1, ConvergenceTestsWith1CLB,
    filter_and_change=ConvergenceTestsWith1CLB._only_oob_del_and_error_tests)


class ConvergenceTestsWith2CLBs(unittest.TestCase):
    """
    Tests that require a two load balancers.
    """
    timeout = 1800

    def setUp(self):
        """Establish an HTTP connection pool and commonly used resources for
        each test.  The HTTP connection pool is important for maintaining a
        clean Twisted reactor.
        """
        self.helper = TestHelper(self, num_clbs=2)
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
            for clb in self.helper.clbs])
        )

    @classmethod
    def _only_delete_clb_while_scaling(cls, name, method):
        """
        To be used by :func:`copy_test_methods` to filter only certain
        single-CLB tests (the where the CLB is deleted before scaling)

        This filters out only the tests tagged CATC-020, because that is the
        number in the original test plan corresponding to the CLB deletion test
        case.
        """
        if "CATC-020" in getattr(method, 'tags', ()):
            return (name.replace("all_loadbalancers", "one_loadbalancer"),
                    method)


copy_test_methods(
    ConvergenceTestsWith1CLB, ConvergenceTestsWith2CLBs,
    filter_and_change=ConvergenceTestsWith2CLBs._only_delete_clb_while_scaling)
