"""Contains reusable classes relating to nova."""
import json

from characteristic import Attribute, attributes

import treq

from twisted.internet.defer import gatherResults

from otter.util.http import check_success, headers


@attributes(["id",
             Attribute("pool", default_value=None),
             Attribute("treq", default_value=treq)])
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
        return self.treq.delete(
            "{}/servers/{}".format(rcs.endpoints["nova"], self.id),
            headers=headers(str(rcs.token)),
            pool=self.pool
        ).addCallback(check_success, [204]).addCallback(self.treq.content)

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


def delete_servers(server_ids, rcs, pool=None, _treq=treq):
    """
    Use Nova to delete multiple servers.

    :param iterable server_ids: The IDs of the servers to delete
    """
    return gatherResults([NovaServer(id=_id, pool=pool, treq=_treq).delete(rcs)
                          for _id in server_ids])
