"""
Test self heal service
"""

import os

from testtools.matchers import ContainsDict, Equals, MatchesListwise, NotEquals

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from otter.integration.lib.autoscale import extract_active_ids
from otter.integration.lib.nova import NovaServer
from otter.integration.lib.resources import TestResources
from otter.integration.lib.trial_tools import (
    TestHelper,
    convergence_exec_time,
    get_identity,
    get_resource_mapping,
    region,
    skip_if
)


def only_server_id(rcs, group):
    """
    Extract only server id in the group
    """
    d = group.get_scaling_group_state(rcs, [200])
    return d.addCallback(lambda (_, state): extract_active_ids(state)[0])


class SelfHealTests(TestCase):

    def setUp(self):
        self.helper = TestHelper(self)
        self.rcs = TestResources()
        self.identity = get_identity(self.helper.pool)
        return self.identity.authenticate_user(
            self.rcs,
            resources=get_resource_mapping(),
            region=region
        )

    @skip_if(lambda: "AS_SELFHEAL_INTERVAL" not in os.environ,
             "AS_SELFHEAL_INTERVAL environment variable needed")
    @inlineCallbacks
    def test_selfheal(self):
        """
        SelfHeal service will replace deleted server
        """
        sh_interval = float(os.environ["AS_SELFHEAL_INTERVAL"])
        group, _ = self.helper.create_group(min_entities=1)
        yield group.start(self.rcs, self)
        yield group.wait_for_state(
            self.rcs, ContainsDict({"activeCapacity": Equals(1)}))
        # delete server OOB
        server_id = yield only_server_id(self.rcs, group)
        yield NovaServer(id=server_id, pool=self.helper.pool).delete(self.rcs)
        # Wait for new server to come back up by self heal service. It can
        # take 2 * selfheal interval because the new group may get scheduled
        # to be triggered after last scheduling is already setup
        yield group.wait_for_state(
            self.rcs,
            ContainsDict(
                {"active": MatchesListwise([
                    ContainsDict({"id": NotEquals(server_id)})])}),
            timeout=(sh_interval + convergence_exec_time) * 2)
        # Delete new server again and see if it comes back. It should be
        # back within selfheal interval
        server_id = yield only_server_id(self.rcs, group)
        yield NovaServer(id=server_id, pool=self.helper.pool).delete(self.rcs)
        yield group.wait_for_state(
            self.rcs,
            ContainsDict(
                {"active": MatchesListwise([
                    ContainsDict({"id": NotEquals(server_id)})])}),
            timeout=sh_interval + convergence_exec_time)
