"""Steps for convergence."""

from characteristic import attributes
from zope.interface import implementer, Interface

from otter.constants import ServiceType
from otter.util.http import append_segments


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_request():
        """
        Create a :class:`Request` object that contains relevant information for
        performing the HTTP request required for this step
        """


@implementer(IStep)
@attributes(['launch_config'])
class CreateServer(object):
    """
    A server must be created.

    :ivar pmap launch_config: Nova launch configuration.
    """

    def as_request(self):
        """Produce a :obj:`Request` to create a server."""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='POST',
            path='servers',
            data=self.launch_config)


@implementer(IStep)
@attributes(['server_id'])
class DeleteServer(object):
    """
    A server must be deleted.

    :ivar str server_id: a Nova server ID.
    """

    def as_request(self):
        """Produce a :obj:`Request` to delete a server."""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='DELETE',
            path=append_segments('servers', self.server_id))


@implementer(IStep)
@attributes(['server_id', 'key', 'value'])
class SetMetadataItemOnServer(object):
    """
    A metadata key/value item must be set on a server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)
    """
    def as_request(self):
        """Produce a :obj:`Request` to set a metadata item on a server"""
        return Request(
            service=ServiceType.CLOUD_SERVERS,
            method='PUT',
            path=append_segments('servers', self.server_id, 'metadata',
                                 self.key),
            data={'meta': {self.key: self.value}})


@implementer(IStep)
@attributes(['lb_id', 'address_configs'])
class AddNodesToLoadBalancer(object):
    """
    Multiple nodes must be added to a load balancer.

    :param address_configs: A collection of two-tuples of address and
        :obj:`LBConfig`.
    """
    def as_request(self):
        """Produce a :obj:`Request` to add nodes to CLB"""
        return Request(
            service=ServiceType.CLOUD_LOAD_BALANCERS,
            method='POST',
            path=append_segments('loadbalancers', str(self.lb_id)),
            data={'nodes': [{'address': address, 'port': lbc.port,
                             'condition': lbc.condition.name, 'weight': lbc.weight,
                             'type': lbc.type.name}
                            for address, lbc in self.address_configs]})


@implementer(IStep)
@attributes(['lb_id', 'node_id'])
class RemoveFromLoadBalancer(object):
    """
    A server must be removed from a load balancer.
    """

    def as_request(self):
        """Produce a :obj:`Request` to remove a load balancer node."""
        return Request(
            service=ServiceType.CLOUD_LOAD_BALANCERS,
            method='DELETE',
            path=append_segments('loadbalancers',
                                 str(self.lb_id),
                                 str(self.node_id)))


@implementer(IStep)
@attributes(['lb_id', 'node_id', 'condition', 'weight', 'type'])
class ChangeLoadBalancerNode(object):
    """
    An existing port mapping on a load balancer must have its condition,
    weight, or type modified.
    """

    def as_request(self):
        """Produce a :obj:`Request` to modify a load balancer node."""
        return Request(
            service=ServiceType.CLOUD_LOAD_BALANCERS,
            method='PUT',
            path=append_segments('loadbalancers',
                                 self.lb_id,
                                 'nodes', self.node_id),
            data={'condition': self.condition,
                  'weight': self.weight})


def _rackconnect_bulk_request(lb_node_pairs, method, success_codes):
    """
    Creates a bulk request for RackConnect v3.0 load balancers.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made or broken.
    :param str method: The method of the request ``"DELETE"`` or
        ``"POST"``.
    :param iterable success_codes: Status codes considered successful for this request.
    :return: A bulk RackConnect v3.0 request for the given load balancer,
        node pairs.
    :rtype: :class:`Request`
    """
    return Request(
        service=ServiceType.RACKCONNECT_V3,
        method=method,
        path=append_segments("load_balancer_pools",
                             "nodes"),
        data=[{"cloud_server": {"id": node},
               "load_balancer_pool": {"id": lb}}
              for (lb, node) in lb_node_pairs],
        success_codes=success_codes)


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkAddToRCv3(object):
    """
    Some connections must be made between some combination of servers
    and RackConnect v3.0 load balancers.

    Each connection is independently specified.

    See http://docs.rcv3.apiary.io/#post-%2Fv3%2F{tenant_id}%2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made.
    """

    def as_request(self):
        """
        Produce a :obj:`Request` to add some nodes to some RCv3 load
        balancers.
        """
        return _rackconnect_bulk_request(self.lb_node_pairs, "POST", (201,))


@implementer(IStep)
@attributes(['lb_node_pairs'])
class BulkRemoveFromRCv3(object):
    """
    Some connections must be removed between some combination of nodes
    and RackConnect v3.0 load balancers.

    See http://docs.rcv3.apiary.io/#delete-%2Fv3%2F{tenant_id}%2Fload_balancer_pools%2Fnodes.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be removed.
    """

    def as_request(self):
        """
        Produce a :obj:`Request` to remove some nodes from some RCv3 load
        balancers.
        """
        return _rackconnect_bulk_request(self.lb_node_pairs, "DELETE", (204,))


@attributes(['service', 'method', 'path', 'headers', 'data', 'success_codes'],
            defaults={'headers': None, 'data': None, 'success_codes': (200,)})
class Request(object):
    """
    An object representing a Rackspace API request that must be performed.

    A :class:`Request` only stores information - something else must use the
    information to make an HTTP request, as a :class:`Request` itself has no
    behaviors.

    :ivar ServiceType service: The Rackspace service that the request
        should be sent to. One of the members of :obj:`ServiceType`.
    :ivar bytes method: The HTTP method.
    :ivar bytes path: The path relative to a tenant namespace provided by the
        service.  For example, for cloud servers, this path would be appended
        to something like
        ``https://dfw.servers.api.rackspacecloud.com/v2/010101/`` and would
        therefore typically begin with ``servers/...``.
    :ivar dict headers: a dict mapping bytes to lists of bytes.
    :ivar object data: a Python object that will be JSON-serialized as the body
        of the request.
    :ivar iterable<int> success_codes: The status codes that will be considered
        successful. Defaults to just 200 (OK). Requests that expect other codes,
        such as 201 (Created) for most ``POST`` requests or 204 (No content)
        for most ``DELETE`` requests should specify that through this argument.
    """
