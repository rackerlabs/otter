"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

from __future__ import print_function

import os
from functools import wraps

from testtools.matchers import (
    AllMatch, ContainsDict, Equals, MatchesAll, MatchesSetwise, NotEquals)

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
from otter.integration.lib.mimic import MimicCLB, MimicNova
from otter.integration.lib.nova import (
    NovaServer, delete_servers, wait_for_servers)
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
mimic_clb_key = os.environ.get("MIMICCLB_SC_KEY", 'cloudLoadBalancerControl')

# otter configuration options for testing
otter_build_timeout = float(os.environ.get("AS_BUILD_TIMEOUT_SECONDS", "30"))


def not_mimic():
    """
    Return True unless the environment variable AS_USING_MIMIC is set to
    something truthy.
    """
    return not bool(os.environ.get("AS_USING_MIMIC", False))


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
        :return: a tuple of the scaling group with (the helper's pool) and
            the server name prefix used for the scaling group.
        """
        if self.clbs:
            kwargs['use_lbs'] = [clb.scaling_group_spec() for clb in self.clbs]

        server_name_prefix = "{}-{}".format(
            random_string(), reactor.seconds())
        if "server_name_prefix" in kwargs:
            server_name_prefix = "{}-{}".format(kwargs['server_name_prefix'],
                                                server_name_prefix)
        kwargs['server_name_prefix'] = server_name_prefix

        return (
            ScalingGroup(
                group_config=create_scaling_group_dict(**kwargs),
                pool=self.pool),
            server_name_prefix)

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
    module skips the whole test module.

    This should be added upstream to Twisted trial.
    """
    def decorate(function):
        function.skip = reason
        return function
    return decorate


def skip_if(predicate, reason):
    """
    Decorator that skips a test method or test class by setting the property
    "skip", and only if the provided predicate evaluates to True.
    """
    if predicate():
        return skip_me(reason)
    return lambda f: f


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


def random_string(byte_len=4):
    """
    Generate a random string of the ``byte_len``.
    The string will be 2 * ``byte_len`` in length.
    """
    return os.urandom(byte_len).encode('hex')


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

    @skip_me("Autoscale does not clean up servers deleted OOB yet. See #881.")
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

    @skip_me("Autoscale does not clean up servers deleted OOB yet. See #881.")
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
            self.helper.clbs = [self.clb]
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
            return _oob_disable_then(
                self.helper, rcs, num_to_disable=2, disabler=_deleter,
                then=_scale_by(1), max_servers=scaling_group_max_entities,
                desired_servers=24, final_servers=25)

        return create_clb_first().addCallback(then_test)

    def _remove_metadata(self, ids, rcs):
        """Given a list of server IDs, use Nova to remove their metadata.
        This will strip them of their association with Autoscale.
        """
        self.removed_ids = ids
        return gatherResults([
            NovaServer(id=_id, pool=self.helper.pool).update_metadata({}, rcs)
            for _id in ids]).addCallback(lambda _: rcs)


@inlineCallbacks
def _oob_disable_then(helper, rcs, num_to_disable, disabler, then,
                      min_servers=0, max_servers=25, desired_servers=None,
                      final_servers=None):
    """
    Helper function that tests that convergence will heal out-of-band disabling
    of servers, whether by deletion, or errors.

    1.  Creates a scaling group with the given min and max entities.
    2.  If ``desired_servers`` is provided, sets the desired capacity to
        ``desired_servers`` using a scaling policy.
    3.  Waits for those servers (either ``desired_servers`` or ``min_servers``
        to become active and added to any load balancers.
    4.  Disable ``num_to_disable`` random servers using the provided function,
        ``disabler``.
    5.  Executes the function provided by the parameter ``then``.
    6.  Waits for:
        - ``final_servers`` active servers that are all on the requisite load
          balancers.
        - the disabled servers to have been removed from the active server list
        - the disabled servers to have been removed from any load balancers
        - the group to be in ACTIVE state

    :param TestHelper helper: An instance of :class:`TestHelper`
    :param TestResources rcs: An instance of
        :class:`otter.integration.lib.resources.TestResources`
    :param int num_to_disable: How many servers to out-of-band disable.
    :param callable disabler: Function that takes the helper, rcs, and an
        iterable of server IDs, and disables them somehow, either by deleting
        them, erroring them, or disassociating them from the group.
    :param callable then: Function that takes a helper, RCS, and group, and
        does something (such as scale up or trigger convergence).

    :param int min_servers: The min entities for the scaling group - defaults
        to zero.
    :param int max_servers: The min entities for the scaling group - defaults
        to 25.
    :param int desired_servers: The initial desired capacity of the scaling
        group.  If not provided, by default, the scaling group will just start
        out with the minimum number of servers. If provided, immediately after
        creation the group will be scaled to this number before any deletions
        or other scaling occurs.
    :param int final_servers: The number of servers to expect at the end as
        both active and desired servers.  If not passed, defaults to the
        number of desired servers, or min servers.

    :return: The scaling group that was created and tested.
    """
    scaling_group, _ = helper.create_group(
        image_ref=image_ref, flavor_ref=flavor_ref,
        min_entities=min_servers, max_entities=max_servers
    )

    yield helper.start_group_and_wait(scaling_group, rcs,
                                      desired=desired_servers)

    to_disable = yield scaling_group.choose_random_servers(rcs, num_to_disable)

    ips = {}
    if helper.clbs:
        ips = yield scaling_group.get_servicenet_ips(rcs, to_disable)

    yield disabler(helper, rcs, to_disable)
    yield then(helper, rcs, scaling_group)

    if final_servers is None:
        final_servers = (
            min_servers if desired_servers is None else desired_servers)

    end_state = [scaling_group.wait_for_state(
        rcs,
        MatchesAll(
            HasActive(final_servers),
            ContainsDict({
                'pendingCapacity': Equals(0),
                'desiredCapacity': Equals(final_servers)
            }),
            ExcludesServers(to_disable)
        ),
        timeout=600
    )]

    if helper.clbs:
        end_state += [clb.wait_for_nodes(rcs, ExcludesAllIPs(ips.values()),
                                         timeout=600)
                      for clb in helper.clbs]

    yield gatherResults(end_state)
    returnValue(scaling_group)


def _deleter(helper, rcs, server_ids):
    """
    A disabler function to be passed to :func:`_oob_disable_then` that deletes
    the servers out of band.
    """
    return delete_servers(server_ids, rcs, pool=helper.pool)


def _errorer(helper, rcs, server_ids):
    """
    A disabler function to be passed to :func:`_oob_disable_then` that invokes
    Mimic to set the server statuses to "ERROR"
    """
    return MimicNova(pool=helper.pool).change_server_statuses(
        rcs, {server_id: "ERROR" for server_id in server_ids})


def _scale_by(number, should_fail=False):
    """
    A helper function that creates a scaling policy and scales by the given
    number, if the number is not zero.  Otherwise, just triggers convergence.

    :param int number: The number to scale by.
    :param bool should_fail: Whether or not the policy execution should fail.
    :return: A function that can be passed to :func:`_oob_disable_then` as the
        ``then`` parameter.
    """
    def _then(helper, rcs, group):
        policy = ScalingPolicy(scale_by=number, scaling_group=group)
        return (policy.start(rcs, helper.test_case)
                .addCallback(policy.execute,
                             success_codes=[403] if should_fail else [202]))
    return _then


def _converge(helper, rcs, group):
    """
    Function to be passed to :func:`_oob_disable_then` as the ``then``
    parameter that triggers convergence.
    """
    return group.trigger_convergence(rcs)


class ConvergenceTestsNoLBs(unittest.TestCase):
    """
    Class for convergence tests that do not require any load balancers.
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
        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=2,
            disabler=_deleter, then=_converge, min_servers=4,
            final_servers=4)

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
        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=1, disabler=_deleter,
            then=_scale_by(2), min_servers=3, final_servers=5)

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=z, disabler=_deleter,
            then=_scale_by(y), min_servers=N, desired_servers=x,
            final_servers=(x + y))

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=z, disabler=_deleter,
            then=_scale_by(y), min_servers=N, desired_servers=x,
            final_servers=(x + y))

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=z, disabler=_deleter,
            then=_scale_by(y), min_servers=N, desired_servers=x,
            final_servers=(x + y))

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=z, disabler=_deleter,
            then=_scale_by(y, should_fail=True),
            max_servers=max_servers, desired_servers=x,
            final_servers=max_servers)

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=z, disabler=_deleter,
            then=_scale_by(y, should_fail=True),
            min_servers=min_servers, final_servers=min_servers)

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

        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=set_to_servers / 2,
            disabler=_deleter,
            then=lambda helper, rcs, group: group.update_group_config(
                rcs, maxEntities=max_servers + 2),
            max_servers=max_servers, desired_servers=set_to_servers,
            final_servers=set_to_servers)

    @tag("CATC-009")
    def test_convergence_fixes_errored_building_servers(self):
        """
        CATC-009

        If a server transitions into ERROR status from BUILD status,
        convergence will clean it up and create a new server to replace it.

        Checks nova to make sure that convergence has not overprovisioned.
        """
        group, server_name_prefix = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=2, max_entities=10,
            server_name_prefix="build-to-error"
        )
        mimic_nova = MimicNova(pool=self.helper.pool, test_case=self)
        d = mimic_nova.sequenced_behaviors(
            self.rcs,
            criteria=[{"server_name": server_name_prefix + ".*"}],
            behaviors=[
                {"name": "error", "parameters": {}},
                {"name": "default"},
                {"name": "default"}
            ])
        d.addCallback(
            lambda _: self.helper.start_group_and_wait(group, self.rcs))
        d.addCallback(wait_for_servers, pool=self.helper.pool, group=group,
                      matcher=HasLength(2), timeout=600)
        d.addCallback(lambda _: group)
        return d

    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-010")
    @inlineCallbacks
    def test_servers_that_build_for_too_long_time_out_and_are_replaced(self):
        """
        CATC-010

        1. Mimic should cause a single server to remain in building too
           long.
        2. Create group with 2 servers.  (One of them will time out building.)
        3. Check with Nova that 2 servers are built - wait for one to be
           active.  The other is the one that should remain in build.
        4. Wait for autoscale to show 2 servers being active.
        5. Check with Nova to ensure that there are only 2 active servers on
           the account.  The one that was building forever should be deleted.
        """
        group, server_name_prefix = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=2, max_entities=10,
            server_name_prefix="build-timeout"
        )
        mimic_nova = MimicNova(pool=self.helper.pool, test_case=self)
        yield mimic_nova.sequenced_behaviors(
            self.rcs,
            criteria=[{"server_name": server_name_prefix + ".*"}],
            behaviors=[
                {"name": "build",
                 "parameters": {"duration": otter_build_timeout * 2}},
                {"name": "default"},
                {"name": "default"}
            ])
        yield group.start(self.rcs, self)

        initial_servers = yield wait_for_servers(
            self.rcs, pool=self.helper.pool, group=group,
            timeout=otter_build_timeout,
            matcher=MatchesSetwise(
                ContainsDict({'status': Equals('ACTIVE')}),
                ContainsDict({'status': Equals('BUILD')}),
            ))

        # the above ensures that there is one server with status BUILD
        building_server_id = next(s['id'] for s in initial_servers
                                  if s['status'] == 'BUILD')

        yield group.wait_for_state(
            self.rcs,
            MatchesAll(
                ContainsDict({
                    'pendingCapacity': Equals(0),
                    'desiredCapacity': Equals(2),
                    'status': Equals("ACTIVE")
                }),
                HasActive(2),
                ExcludesServers([building_server_id])),
            timeout=600)

        yield wait_for_servers(
            self.rcs, pool=self.helper.pool, group=group,
            timeout=600,
            matcher=MatchesAll(
                AllMatch(ContainsDict({'status': Equals('ACTIVE'),
                                       'id': NotEquals(building_server_id)})),
                HasLength(2)
            ))
        returnValue(group)

    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-011")
    def test_scale_up_after_servers_error_from_active(self):
        """
        CATC-011

        1. Create a scaling group with N min servers and M max servers.
        2. After the servers are active, E go into error state.
        3. Scale up by (N-M).
        4. Assert that there should be M active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=1, disabler=_errorer,
            then=_scale_by(2), min_servers=2, max_servers=4, final_servers=4)

    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-012")
    def test_scale_down_after_servers_error_from_active(self):
        """
        CATC-012

        1. Create a scaling group with N min servers and M max servers.
        2. Set the number of servers to be X (N<X<M)
        2. After the servers are active, E go into error state (E>(X-N))
        3. Scale down to N servers on the group.
        4. Assert that there should be N active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=2, disabler=_errorer,
            then=_scale_by(-1), min_servers=2, max_servers=4,
            desired_servers=3, final_servers=2)

    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-013")
    def test_trigger_convergence_after_servers_error_from_active(self):
        """
        CATC-013

        1. Create a scaling group with N min servers and M max servers.
        2. Set the number of servers to be X (N<X<M)
        2. After the servers are active, E go into error state (E<(X-N))
        3. Trigger a convergence cycle.
        4. Assert that there should be X active servers on the group, and
           that the active servers do not include the ones that errored.
        """
        return _oob_disable_then(
            self.helper, self.rcs, num_to_disable=2, disabler=_errorer,
            then=_converge, min_servers=2, max_servers=4,
            desired_servers=3, final_servers=3)

    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-029")
    def test_false_negative_on_server_create_from_nova_no_overshoot(self):
        """
        CATC-029

        Nova returns 500 on server create, but creates the server anyway.
        Convergence does not overprovision servers as a result.

        Checks nova to make sure that convergence has not overprovisioned.
        """
        group, server_name_prefix = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=2, max_entities=10,
            server_name_prefix="false-negative"
        )
        mimic_nova = MimicNova(pool=self.helper.pool, test_case=self)
        d = mimic_nova.sequenced_behaviors(
            self.rcs,
            criteria=[{"server_name": server_name_prefix + ".*"}],
            behaviors=[
                {"name": "false-negative",
                 "parameters": {"code": 500,
                                "message": "Server creation failed."}},
                {"name": "default"},
                {"name": "default"}
            ])
        d.addCallback(
            lambda _: self.helper.start_group_and_wait(group, self.rcs))
        d.addCallback(wait_for_servers, pool=self.helper.pool, group=group,
                      matcher=HasLength(2), timeout=600)
        return d


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

    :param TestResources rcs: An instance of
        :class:`otter.integration.lib.resources.TestResources`
    :param ScalingGroup group: An instance of
        :class:`otter.integration.lib.autoscale.ScalingGroup` to start -
        this group should not have been started already.
    :param int scale_by: How much to scale by.  This is assumed to never be
        zero.  If it is zero, this function will fail because autoscale
        prevents the creation of a policy that scales by zero.
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
                "mimic_nova": (mimic_nova_key,),
                "mimic_clb": (mimic_clb_key,)
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

    @skip_me("Mimic does not support CLB limits, skipped pending Mimic #291")
    @tag("CATC-019")
    def test_scale_over_lb_limit(self):
        """
        CATC-019-a: Validate that when a group attempts to scale over the
        load balancer limit the group enters an error state. It is expected
        that the active capacity will match the maximum allowed on the load
        balancer and the pending capacity will become zero once the group is
        in ERROR state.

        1. Creates a scaling group with a load balancer and max servers
           greater than the load balancer max. (Assume LB_max == 25)
        2. Scale up to a desired capacity greater than the LB_max
        3. Assert that the scaling group goes into error state, that the
           active count is equal to LB_max, and that no servers are pending.

        """
        LB_max = 25
        group_max = 30

        group = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref, min_entities=1,
            max_entities=group_max)

        scale_up_to_group_max = ScalingPolicy(
            set_to=group_max,
            scaling_group=group
        )

        return (
            self.helper.start_group_and_wait(group, self.rcs,
                                             desired=LB_max - 5)
            .addCallback(scale_up_to_group_max.start, self)
            .addCallback(scale_up_to_group_max.execute)
            .addCallback(
                group.wait_for_state,
                MatchesAll(
                    ContainsDict({
                        'pendingCapacity': Equals(0),
                        'desiredCapacity': Equals(group_max),
                        'status': Equals("ERROR")
                    }),
                    HasActive(LB_max)),
                timeout=600
            )
        )

    @tag("CATC-020")
    def test_delete_all_loadbalancers_and_scale_up(self, delete_clb=None):
        """
        CATC-020-a. This will also be tested with 2 load balancers.

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
        group, _ = self.helper.create_group(
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
        CATC-020-b.  This will also be tested with 2 load balancers.

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
        group, _ = self.helper.create_group(
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

    # @skip_me("Otter does not yet support this error transition")
    @skip_if(not_mimic, "This requires Mimic for error injection.")
    @tag("CATC-023")
    def test_clb_plane(self):
        """
        CATC-023-a: Validate that Otter correctly enters an error state when
        attemting to scale up while the CLB is in the PENDING_DELETE state.

        1. Create a group with non-min servers attached to a CLB
        2. Place the CLB into the PENDING_DELETE state
            - Return 422, status: PENDING_DELETE on any mutating request
        3. Scale up
        4. Assert that the group goes into error state since it cannot
            take action.
        """
        group, _ = self.helper.create_group(
            image_ref=image_ref, flavor_ref=flavor_ref, min_entities=1)

        mimic_clb = MimicCLB(pool=self.helper.pool, test_case=self)

        policy_scale_up = ScalingPolicy(
            scale_by=1,
            scaling_group=group
        )

        return (
            self.helper.start_group_and_wait(group, self.rcs)
            .addCallback(
                mimic_clb.set_clb_attributes,
                self.helper.clbs[0].clb_id, {"status": "PENDING_DELETE"})
            .addCallback(lambda _: self.rcs)
            .addCallback(policy_scale_up.start, self)
            .addCallback(policy_scale_up.execute)
            .addCallback(
                group.wait_for_state,
                MatchesAll(
                    ContainsDict({
                        'status': Equals("ERROR")
                    })),
                timeout=600
            )
        )

copy_test_methods(
    ConvergenceTestsNoLBs, ConvergenceTestsWith1CLB,
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
