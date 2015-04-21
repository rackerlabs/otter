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

    def test_reaction_to_oob_deletion_then_scale_up(self):
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
    test_reaction_to_oob_deletion_then_scale_up.timeout = 1800

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
            .addCallback(lambda _: self.removed_ids)
            .addCallback(
                self.scaling_group.wait_for_deleted_id_removal,
                rcs,
                total_servers=N_SERVERS,
            )
        )
    test_reaction_to_oob_server_deletion.timeout = 1800

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
        self.removed_ids = ids
        # If no error occurs while deleting, all the results will be the
        # same.  So just return the 1st, which is just our rcs value.
        return gatherResults(deferreds).addCallback(lambda rslts: rslts[0])
