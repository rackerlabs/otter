"""Steps for convergence."""

import re

from characteristic import attributes

from effect import Effect, Func

from pyrsistent import thaw

from zope.interface import Interface, implementer

from otter.constants import ServiceType
from otter.http import has_code, service_request
from otter.util.hashkey import generate_server_name
from otter.util.http import append_segments


class IStep(Interface):
    """
    An :obj:`IStep` is a step that may be performed within the context of a
    converge operation.
    """

    def as_effect():
        """Return an Effect which performs this step."""


def set_server_name(server_config_args, name_suffix):
    """
    Append the given name_suffix to the name of the server in the server
    config.

    :param server_config_args: The server configuration args.
    :param name_suffix: the suffix to append to the server name. If no name was
        specified, it will be used as the name.
    """
    name = server_config_args['server'].get('name')
    if name is not None:
        name = '{0}-{1}'.format(name, name_suffix)
    else:
        name = name_suffix
    return server_config_args.set_in(('server', 'name'), name)


@implementer(IStep)
@attributes(['server_config'])
class CreateServer(object):
    """
    A server must be created.

    :ivar pmap server_config: Nova launch configuration.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to create a server."""
        eff = Effect(Func(generate_server_name))

        def got_name(random_name):
            server_config = set_server_name(self.server_config, random_name)
            return service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data=thaw(server_config))
        return eff.on(got_name)


@implementer(IStep)
@attributes(['server_id'])
class DeleteServer(object):
    """
    A server must be deleted.

    :ivar str server_id: a Nova server ID.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to delete a server."""
        return service_request(
            ServiceType.CLOUD_SERVERS,
            'DELETE',
            append_segments('servers', self.server_id))


@implementer(IStep)
@attributes(['server_id', 'key', 'value'])
class SetMetadataItemOnServer(object):
    """
    A metadata key/value item must be set on a server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)
    """
    def as_effect(self):
        """Produce a :obj:`Effect` to set a metadata item on a server"""
        return service_request(
            ServiceType.CLOUD_SERVERS,
            'PUT',
            append_segments('servers', self.server_id, 'metadata', self.key),
            data={'meta': {self.key: self.value}})


@implementer(IStep)
@attributes(['lb_id', 'address_configs'])
class AddNodesToCLB(object):
    """
    Multiple nodes must be added to a load balancer.

    :param address_configs: A collection of two-tuples of address and
        :obj:`CLBDescription`.
    """
    def as_effect(self):
        """Produce a :obj:`Effect` to add nodes to CLB"""
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'POST',
            append_segments('loadbalancers', str(self.lb_id)),
            data={'nodes': [{'address': address, 'port': lbc.port,
                             'condition': lbc.condition.name,
                             'weight': lbc.weight,
                             'type': lbc.type.name}
                            for address, lbc in self.address_configs]})


@implementer(IStep)
@attributes(['lb_id', 'node_id'])
class RemoveFromCLB(object):
    """
    A server must be removed from a load balancer.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to remove a load balancer node."""
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            append_segments('loadbalancers', str(self.lb_id),
                            str(self.node_id)))


@implementer(IStep)
@attributes(['lb_id', 'node_id', 'condition', 'weight', 'type'])
class ChangeCLBNode(object):
    """
    An existing port mapping on a load balancer must have its condition,
    weight, or type modified.
    """

    def as_effect(self):
        """Produce a :obj:`Effect` to modify a load balancer node."""
        return service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'PUT',
            append_segments('loadbalancers', self.lb_id,
                            'nodes', self.node_id),
            data={'condition': self.condition,
                  'weight': self.weight})


def _rackconnect_bulk_request(lb_node_pairs, method, success_pred):
    """
    Creates a bulk request for RackConnect v3.0 load balancers.

    :param list lb_node_pairs: A list of ``lb_id, node_id`` tuples of
        connections to be made or broken.
    :param str method: The method of the request ``"DELETE"`` or
        ``"POST"``.
    :param success_pred: Predicate that determines if a response was
        successful.
    :return: A bulk RackConnect v3.0 request for the given load balancer,
        node pairs.
    :rtype: :class:`Request`
    """
    return service_request(
        ServiceType.RACKCONNECT_V3,
        method,
        append_segments("load_balancer_pools", "nodes"),
        data=[{"cloud_server": {"id": node},
               "load_balancer_pool": {"id": lb}}
              for (lb, node) in lb_node_pairs],
        success_pred=success_pred)


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

    def as_effect(self):
        """
        Produce a :obj:`Effect` to add some nodes to some RCv3 load
        balancers.
        """
        return _rackconnect_bulk_request(
            self.lb_node_pairs, "POST",
            success_pred=has_code(201))


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

    def as_effect(self):
        """
        Produce a :obj:`Effect` to remove some nodes from some RCv3 load
        balancers.
        """
        eff = _rackconnect_bulk_request(self.lb_node_pairs, "DELETE",
                                        success_pred=has_code(204, 409))
        # While 409 isn't success, that has to be introspected by
        # _rcv3_check_bulk_delete in order to recover from it.
        return eff.on(_rcv3_check_bulk_delete)


_UUID4_REGEX = ("[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}"
                "-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}")
_RCV3_NODE_NOT_A_MEMBER_PATTERN = re.compile(
    "Node (?P<node_id>{uuid}) is not a member of Load Balancer Pool "
    "(?P<lb_id>{uuid})".format(uuid=_UUID4_REGEX),
    re.IGNORECASE)


def _rcv3_check_bulk_delete(result):
    """
    Checks if the RCv3 bulk deletion command was successful.

    The request is considered successful if the response code
    indicated unambiguous success, or the machine we're trying to
    remove is already removed anyway.

    If the machine was already removed, returns the next step to try
    and remove the remaining pairs, unless a fatal error *also*
    occurred. This is necessary because RCv3 bulk requests are
    atomic-ish.
    """
    response, body = result

    if response.code == 204:  # All done!
        return

    pairs_to_delete = []
    for error in body["errors"]:
        match = _RCV3_NODE_NOT_A_MEMBER_PATTERN.match(error)
        if not match:  # Unrecoverable error, bail!
            return

        node_id, lb_id = match.groups()
        pairs_to_delete.append((lb_id, node_id))

    next_step = BulkRemoveFromRCv3(lb_node_pairs=pairs_to_delete)
    return next_step.as_effect()
