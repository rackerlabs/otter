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
    ScalingGroup,
    ScalingPolicy,
    create_scaling_group_dict,
    extract_active_ids,
)
from otter.integration.lib.identity import IdentityV2
from otter.integration.lib.resources import TestResources

from otter.util.http import check_success, headers


username = os.environ['AS_USERNAME']
password = os.environ['AS_PASSWORD']
endpoint = os.environ['AS_IDENTITY']
flavor_ref = os.environ['AS_FLAVOR_REF']
image_ref = os.environ['AS_IMAGE_REF']
region = os.environ['AS_REGION']
ce_tenant = "000000"  # Convergnece Enabled Tenant


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

    def test_reaction_to_oob_deletion_after_scale_up(self):
        """Exercise out-of-band server deletion, but then scale up afterwards.
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
            self.identity.authenticate_user(rcs, tenant_id="000000")
            .addCallback(
                rcs.find_end_point,
                "otter", "autoscale", region,
                default_url='http://localhost:9000/v1.0/{0}'
            ).addCallback(
                rcs.find_end_point,
                "nova", "cloudServersOpenStack", region
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
            )
            .addCallback(
                self.scaling_group.wait_for_N_servers, 5, timeout=1800
            )
        )
    test_reaction_to_oob_deletion_after_scale_up.timeout = 1800

    def test_reaction_to_oob_server_deletion(self):
        """Exercise out-of-band server deletion.  The goal is to spin up, say,
        eight servers, then use Nova to delete four of them.  We should be able
        to see, over time, more servers coming into existence to replace those
        deleted.
        """
        print "!!! I am Executing!!!"

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
            self.identity.authenticate_user(rcs, tenant_id="000000")
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
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=N_SERVERS,
            )
        )
    test_reaction_to_oob_server_deletion.timeout = 1800

    def test_scale_down_after_oobd_non_constrained(self):
        """
        Validate that when scaling down after an out of band delete (OOBD)
        the group stabilizes at the correct number of servers with
        the deleted
        server taken into account.

            Create a group with min N servers
            Scale group to (N+ x) servers
            Delete z of the servers out of band
            Scale down by (y) servers
            Validate end state of (N + x - y) servers
                TODO: Consider the case where z == y
                - does this produce an error?
        """

        min_servers = 2
        set_to_servers = 7
        oobd_servers = 2
        scale_servers = -3
        # This only applies if not constrained by max/min
        converged_servers = set_to_servers + scale_servers

        rcs = TestResources()

        scaling_group_body = create_scaling_group_dict(
            image_ref=image_ref, flavor_ref=flavor_ref,
            min_entities=min_servers
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
            self.identity.authenticate_user(rcs, tenant_id=ce_tenant)
            .addCallback(
                rcs.find_end_point,
                "otter", "autoscale", region,
                default_url='http://localhost:9000/v1.0/{0}'
            ).addCallback(
                rcs.find_end_point,
                "nova", "cloudServersOpenStack", region
            ).addCallback(self.scaling_group.start, self)
            .addCallback(self.policy_set.start, self)
            .addCallback(self.policy_set.execute)
            .addCallback(
                self.scaling_group.wait_for_N_servers,
                set_to_servers, timeout=1800
            ).addCallback(self.scaling_group.get_scaling_group_state)
            .addCallback(self._choose_servers_from_active_list, oobd_servers)
            .addCallback(self._delete_those_servers, rcs)
            # Until something triggers convergence, it will take a very long
            # time for Otter to notice the deltion, though it should eventually
            # .addCallback(lambda _: self.removed_ids)
            # .addCallback(
            #     self.scaling_group.wait_for_deleted_id_removal,
            #     rcs, timeout=300,
            #     total_servers=set_to_servers,
            # )

            # What if: Trigger convergence manually, servers in building for
            # a time, then execute policy while still building? - All building
            # should be reaped, and one deleted.

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
    test_scale_down_after_oobd_non_constrained.timeout = 600

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

    def _choose_servers_from_active_list(self, (code, response),
                                         num_servers=None):
        """Select the first 'num_servers' of the servers returned by the
        ``get_scaling_group_state`` function.  Record the number of servers
        received in ``active_servers`` attribute. If no num_servers is
        provided, all active servers will be returned.

        If the number of servers requested is less than the number active,
        an error will be raised.
        """

        if code != 200:
            raise Exception("Not 200!; Asking for the state didn't work.")
        ids = map(lambda obj: obj['id'], response['group']['active'])
        self.active_servers = len(ids)
        if num_servers:
            return ids[:num_servers]
        return ids

    def _choose_random_servers(self, (code, response), n):
        """Selects ``n`` randomly selected servers from those returned by the
        ``get_scaling_group_state`` function.
        """

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

        self.deleted_server_ids = ids
        deferreds = map(delete_server_by_id, ids)
        self.removed_ids = ids
        print " removed ids: {0}".format(self.removed_ids)
        # If no error occurs while deleting, all the results will be the
        # same.  So just return the 1st, which is just our rcs value.
        return gatherResults(deferreds).addCallback(lambda rslts: rslts[0])

    # def _wait_for_expected_state(self, _, rcs, timeout=60, period=1,
    #                              active=None, pending=None, desired=None):
    #     """
    #     Repeatedly get the group state until either the specified timeout has
    #     occurred or the specified number of active, pending, and desired
    #     servers is observed. Unspecifed quantities default to None and are
    #     treated as don't cares.
    #     """

    #     def check((code, response)):
    #         if code != 200:
    #             raise BreakLoopException(
    #                 "Could not get the scaling group state"
    #             )

    #         n_active = len(response["group"]["active"])
    #         n_pending = response["group"]["pendingCapacity"]
    #         n_desired = response["group"]["desiredCapacity"]
    #         print "Active: {0}, Pending: {1}, Desired: {2}".format(n_active,
    #                                                                n_pending,
    #                                                                n_desired)

    #         print response["group"]
    #         if ((active is None or active == n_active)
    #                 and
    #                 (pending is None or pending == n_pending)
    #                 and
    #                 (desired is None or desired == n_desired)):
    #             return rcs

    #         raise TransientRetryError()

    #     def poll():
    #         return self.get_scaling_group_state(rcs).addCallback(check)

    #     return retry_and_timeout(
    #         poll, timeout,
    #         can_retry=transient_errors_except(BreakLoopException),
    #         next_interval=repeating_interval(period),
    #         clock=reactor,
    #         deferred_description=(
    #             "Waiting for Autoscale to see expected state of"
    #             "(active, pending, desired) "
    #             "= ({0}, {1}, {2}".format(active, pending, desired)
    #         )
    #     )

    # def _wait_for_id_removal(self, _, rcs, timeout=60, period=1):
    #     """Wait for the converger to recognize the reality of this tenant's
    #     situation and reflect it in the scaling group state accordingly.
    #     """

    #     def check((code, response)):
    #         if code != 200:
    #             raise BreakLoopException(
    #                 "Scaling group appears to have disappeared"
    #             )

    #         print "-------------- Checking Response:   "
    #         print response
    #         # Confirm that the deleted server ids are no longer in the
    #         # server list
    #         # This should be put into a helper function
    #         ids = map(lambda obj: obj['id'], response['group']['active'])

    #         # If none of the deleted server ids are in the active list
    #         for d in self.deleted_server_ids:
    #             if d in ids:
    #                 raise TransientRetryError()
    #             print "... Server {0} is not in active list".format(d)
    #         return rcs

    #         # n_remaining = self.n_servers - self.n_killed + 1
    #         # if len(response["group"]["active"]) == n_remaining:
    #         #     return rcs

    #         # raise TransientRetryError()

    #     def poll():
    #         print "... polling"
    #         return self.get_scaling_group_state(rcs).addCallback(check)

    #     return retry_and_timeout(
    #         poll, timeout,
    #         can_retry=transient_errors_except(BreakLoopException),
    #         next_interval=repeating_interval(period),
    #         clock=reactor,
    #         deferred_description=(
    #             "Waiting for Autoscale to see we killed {} servers of "
    #             "{}.".format(self.n_killed, self.n_servers)
    #         )
    #     )
