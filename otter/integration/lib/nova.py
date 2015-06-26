"""Contains reusable classes relating to nova."""
import json

from characteristic import Attribute, attributes

import treq

from twisted.internet import reactor
from twisted.internet.defer import gatherResults, inlineCallbacks, returnValue
from twisted.python.log import msg

from otter.util.deferredutils import retry_and_timeout
from otter.util.http import APIError, check_success, headers
from otter.util.retry import (
    TransientRetryError,
    repeating_interval,
    terminal_errors_except
)


@attributes(["id", "pool",
             Attribute("treq", default_value=treq),
             Attribute("clock", default_value=reactor)])
class NovaServer(object):
    """
    Represents an existing server in Nova.

    :ivar str id: The nova server ID
    :ivar pool: :class:`twisted.web.client.HTTPConnectionPool`
    :ivar treq: defaults to the `treq` module if not provided - used mainly
        for test injection
    """
    def delete(self, rcs):
        """
        Delete the server.

        :param rcs: an instance of
            :class:`otter.integration.lib.resources.TestResources`
        """
        def try_delete():
            d = self.treq.delete(
                "{}/servers/{}".format(rcs.endpoints["nova"], self.id),
                headers=headers(str(rcs.token)),
                pool=self.pool)
            d.addCallback(check_success, [404], _treq=self.treq)
            d.addCallback(self.treq.content)
            return d

        return retry_and_timeout(
            try_delete, 120,
            can_retry=terminal_errors_except(APIError),
            next_interval=repeating_interval(5),
            clock=self.clock,
            deferred_description=(
                "Waiting for server {} to get deleted".format(self.id)))

    def list_metadata(self, rcs):
        """
        Use Nova to get the server's metadata.

        :param rcs: an instance of
            :class:`otter.integration.lib.resources.TestResources`
        """
        return self.treq.get(
            "{}/servers/{}/metadata".format(rcs.endpoints["nova"], self.id),
            headers=headers(str(rcs.token)),
            pool=self.pool,
        ).addCallback(check_success, [200]).addCallback(self.treq.json_content)

    def update_metadata(self, metadata, rcs):
        """
        Use Nova to alter a server's metadata.

        :param rcs: an instance of
            :class:`otter.integration.lib.resources.TestResources`
        """
        return self.treq.put(
            "{}/servers/{}/metadata".format(rcs.endpoints["nova"], self.id),
            json.dumps({'metadata': metadata}),
            headers=headers(str(rcs.token)),
            pool=self.pool,
        ).addCallback(check_success, [200]).addCallback(self.treq.json_content)

    def get_addresses(self, rcs):
        """
        Get the network addresses for a server.

        :param rcs: an instance of
            :class:`otter.integration.lib.resources.TestResources`
        """
        return self.treq.get(
            "{}/servers/{}/ips".format(rcs.endpoints["nova"], self.id),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, [200]).addCallback(self.treq.json_content)


def delete_servers(server_ids, rcs, pool, _treq=treq):
    """
    Use Nova to delete multiple servers.

    :param iterable server_ids: The IDs of the servers to delete
    """
    return gatherResults([NovaServer(id=_id, pool=pool, treq=_treq).delete(rcs)
                          for _id in server_ids])


def list_servers(rcs, pool, _treq=treq):
    """
    Get a list of all servers, with an optional name regex provided.  This
    does not handle pagination, and instead just increases the limit to an
    absurdly high number.
    """
    params = {'limit': 10000}
    return _treq.get(
        "{}/servers/detail".format(rcs.endpoints['nova']),
        params=params,
        headers=headers(str(rcs.token)),
        pool=pool
    ).addCallback(check_success, [200]).addCallback(_treq.json_content)


def wait_for_servers(rcs, pool, group, matcher, timeout=600, period=10,
                     clock=None, _treq=treq):
    """
    Wait until Nova reaches a particular state (as described by the given
    matcher)with regards to the servers for the given group.

    :param rcs: an instance of
        :class:`otter.integration.lib.resources.TestResources`
    :param pool: a :class:`twisted.web.client.HTTPConnectionPool`
    :param group: a :class:`otter.integration.lib.autoscale.ScalingGroup` that
        specifies which autoscaling group's servers we are looking at.  This
        group should already exist, and have a `group_id` attribute.
    :param matcher: a :mod:`testtools.matcher` matcher that describes the
        desired state of the servers belonging to the autoscaling group.
    """
    @inlineCallbacks
    def do_work():
        servers = yield list_servers(rcs, pool, _treq=_treq)
        servers_in_group = [
            server for server in servers['servers']
            if (group.group_id ==
                server['metadata'].get("rax:autoscale:group:id", None))
        ]
        mismatch = matcher.match(servers_in_group)
        if mismatch:
            msg("Waiting for Nova servers in group {}.\nMismatch: {}"
                .format(group.group_id, mismatch.describe()))
            raise TransientRetryError(mismatch.describe())
        returnValue(servers_in_group)

    return retry_and_timeout(
        do_work, timeout,
        can_retry=terminal_errors_except(TransientRetryError),
        next_interval=repeating_interval(period),
        clock=clock or reactor,
        deferred_description=(
            "Waiting for Nova servers for group {0} to reach state {1}"
            .format(group.group_id, str(matcher)))
    )
