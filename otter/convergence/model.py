"""
Data classes for representing bits of information that need to share a
representation across the different phases of convergence.
"""
import json
import re

import attr
from attr.validators import instance_of, optional

from characteristic import Attribute, attributes

from pyrsistent import PMap, PSet, freeze, pmap, pset, pvector, thaw

from six import string_types

from sumtypes import constructor, sumtype

from toolz.dicttoolz import get_in
from toolz.itertoolz import groupby

from twisted.python.constants import NamedConstant, Names

from zope.interface import Attribute as IAttribute, Interface, implementer

from otter.util.fp import set_in
from otter.util.timestamp import timestamp_to_epoch


class CLBNodeCondition(Names):
    """
    Constants representing the condition a load balancer node can be in.
    """

    ENABLED = NamedConstant()
    """
    The node can accept new connections.
    """

    DRAINING = NamedConstant()
    """
    Node cannot accept any new connections.  Existing connections are
    forcibly terminated.
    """

    DISABLED = NamedConstant()
    """
    Node cannot accept any new connections.  Existing connections are
    permitted to continue.
    """


class CLBNodeType(Names):
    """
    Constants representing the type of a Cloud Load Balancer node.
    """

    PRIMARY = NamedConstant()
    """
    Node in normal rotation.
    """

    SECONDARY = NamedConstant()
    """
    Node only put into normal rotation if a primary node fails.
    """


class ServerState(Names):
    """
    Constants representing the state of a Nova cloud server.

    Most of these constants correspond to Nova states of the same name.
    """
    ACTIVE = NamedConstant()
    BUILD = NamedConstant()
    DELETED = NamedConstant()
    ERROR = NamedConstant()
    HARD_REBOOT = NamedConstant()
    MIGRATING = NamedConstant()
    PASSWORD = NamedConstant()
    REBUILD = NamedConstant()
    RESCUE = NamedConstant()
    RESIZE = NamedConstant()
    REVERT_RESIZE = NamedConstant()
    SHUTOFF = NamedConstant()
    SUSPENDED = NamedConstant()
    UNKNOWN = NamedConstant()
    VERIFY_RESIZE = NamedConstant()

    UNKNOWN_TO_OTTER = NamedConstant()
    """
    Indicates that some state was returned by Nova that Otter doesn't know
    about. The real state will be in `NovaServer.json`.
    """


class StackState(Names):
    CREATE_UPDATE_COMPLETE = NamedConstant()
    CREATE_UPDATE_FAILED = NamedConstant()
    CHECK_COMPLETE = NamedConstant()
    CHECK_FAILED = NamedConstant()
    IN_PROGRESS = NamedConstant()
    DELETED = NamedConstant()
    DELETE_IN_PROGRESS = NamedConstant()
    DELETE_FAILED = NamedConstant()
    OTHER = NamedConstant()  # For states due to out-of-band changes.


class StepResult(Names):
    """
    Constants representing the condition of a step's effect.
    """

    SUCCESS = NamedConstant()
    """
    The step was successful.
    """

    RETRY = NamedConstant()
    """
    Convergence should be retried later.
    """

    LIMITED_RETRY = NamedConstant()
    """
    Converge should be retried, but only a limited number of times.

    This is used when we're waiting for upstream resources to become available
    but aren't certain that they ever will be.
    """

    FAILURE = NamedConstant()
    """
    The step failed. Retrying convergence won't help.
    """


@sumtype
class ConvergenceIterationStatus(object):
    """Result of a single convergence iteration."""
    Stop = constructor()  # Stop converging. Dirty flag can be deleted
    Continue = constructor()  # Continue converging. Don't delete flag.
    GroupDeleted = constructor()  # Group disappeared; force-delete dirty flag.


@sumtype
class ErrorReason(object):
    """A reason for a step to be in a RETRY or FAILURE state."""
    Exception = constructor('exc_info')
    String = constructor(reason=attr.ib(validator=instance_of((unicode, str))))
    Structured = constructor('structure')
    UserMessage = constructor('message')


def get_service_metadata(service_name, metadata):
    """
    Obtain all the metadata associated with a particular service from Nova
    metadata (expecting the schema:  `rax:<service_name>:k1:k2:k3...`).

    :return: the metadata values as a dictionary - in the example above, the
        dictionary would look like `{k1: {k2: {k3: val}}}`
    """
    as_metadata = pmap()
    if isinstance(metadata, dict):
        key_pattern = re.compile(
            "^rax:{service}(?P<subkeys>(:[A-Za-z0-9\-_]+)+)$"
            .format(service=service_name))

        for k, v in metadata.iteritems():
            m = key_pattern.match(k)
            if m:
                subkeys = m.groupdict()['subkeys']
                as_metadata = set_in(
                    as_metadata,
                    [sk for sk in subkeys.split(':') if sk],
                    v)
    return as_metadata


def _private_ipv4_addresses(server):
    """
    Get all private IPv4 addresses from the addresses section of a server.

    :param dict server: A server dict.
    :return: List of IP addresses as strings.
    """
    private_addresses = get_in(["addresses", "private"], server, [])
    return [addr['addr'] for addr in private_addresses if addr['version'] == 4]


def _servicenet_address(server):
    """
    Find the ServiceNet address for the given server.
    """
    return next((ip for ip in _private_ipv4_addresses(server)
                 if ip.startswith("10.")), "")


def _lbs_from_metadata(metadata):
    """
    Get the desired load balancer descriptions based on the metadata.

    :return: ``dict`` of `ILBDescription` providers
    """
    lbs = get_service_metadata('autoscale', metadata).get('lb', {})
    desired_lbs = []

    for lb_id, v in lbs.get('CloudLoadBalancer', {}).iteritems():
        # if malformed, skiped the whole key
        try:
            configs = json.loads(v)
            if isinstance(configs, list):
                desired_lbs.extend([
                    CLBDescription(lb_id=lb_id, port=c['port'])
                    for c in configs])
        except (ValueError, KeyError, TypeError):
            pass

    desired_lbs.extend([
        RCv3Description(lb_id=lb_id) for lb_id in lbs.get('RackConnectV3', {})
    ])

    return pset(desired_lbs)


def _validate_state(_1, _2, state):
    """
    Assert that a state is in ServerState
    """
    if state not in ServerState.iterconstants():
        raise AssertionError("{0} is not a ServerState".format(state))


@attr.s(repr=False)
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.

    :ivar state: Current state of the server.
    :type state: A member of :class:`ServerState`

    :ivar float created: Timestamp at which the server was created.
    :ivar str servicenet_address: The private ServiceNet IPv4 address, if
        the server is on the ServiceNet network
    :ivar str image_id: The ID of the image the server was launched with
    :ivar str flavor_id: The ID of the flavor the server was launched with
    :ivar PSet desired_lbs: An immutable mapping of load balancer IDs to lists
        of :class:`CLBDescription` instances.
    :var dict json: JSON dict received from Nova from which this server
        is created
    """
    id = attr.ib()
    state = attr.ib(validator=_validate_state)
    created = attr.ib()
    image_id = attr.ib()
    flavor_id = attr.ib()
    # type(pvector()) is pvectorc.PVector, which != pyrsistent.PVector
    links = attr.ib(default=attr.Factory(pvector),
                    validator=instance_of(type(pvector())))
    desired_lbs = attr.ib(default=attr.Factory(pset),
                          validator=instance_of(PSet))
    servicenet_address = attr.ib(default='',
                                 validator=instance_of(string_types))
    json = attr.ib(default=attr.Factory(pmap), validator=instance_of(PMap))

    @classmethod
    def from_server_details_json(cls, server_json):
        """
        Create a :obj:`NovaServer` instance from a server details JSON
        dictionary, although without any 'server' or 'servers' initial resource
        key.

        See
        https://docs.rackspace.com/servers/api/v2/cs-devguide/content/
        Get_Server_Details-d1e2623.html

        :return: :obj:`NovaServer` instance
        """
        try:
            server_state = ServerState.lookupByName(server_json['status'])
        except ValueError:
            server_state = ServerState.UNKNOWN_TO_OTTER
        if server_json.get("OS-EXT-STS:task_state", "") == "deleting":
            server_state = ServerState.DELETED
        metadata = server_json.get('metadata', {})

        return cls(
            id=server_json['id'],
            state=server_state,
            created=timestamp_to_epoch(server_json['created']),
            image_id=get_in(["image", "id"], server_json),
            flavor_id=server_json['flavor']['id'],
            links=freeze(server_json['links']),
            desired_lbs=_lbs_from_metadata(metadata),
            servicenet_address=_servicenet_address(server_json),
            json=freeze(server_json))

    def __repr__(self):
        """
        Make the repr a little more friendly - and with less redundant/unused
        information.
        """
        kvpairs = []
        # this gives us an ordered list
        for a in attr.fields(self.__class__):
            value = thaw(getattr(self, a.name))
            if a.name == "json":
                value = {k: v for k, v in value.items() if k in
                         ('status', 'metadata', 'updated', 'name',
                          'OS-EXT-STS:task_state')}
            kvpairs.append("{0}={1}".format(a.name, repr(value)))
        return "<{0}({1})>".format(self.__class__.__name__, ", ".join(kvpairs))

    def __str__(self):
        """Return the repr"""
        return repr(self)


@attr.s
class HeatStack(object):
    action = attr.ib()
    id = attr.ib()
    name = attr.ib()
    status = attr.ib()

    delete_states = {'COMPLETE': StackState.DELETED,
                     'FAILED': StackState.DELETE_FAILED,
                     'IN_PROGRESS': StackState.DELETE_IN_PROGRESS}

    create_update_states = {'COMPLETE': StackState.CREATE_UPDATE_COMPLETE,
                            'FAILED': StackState.CREATE_UPDATE_FAILED}

    check_states = {'COMPLETE': StackState.CHECK_COMPLETE,
                    'FAILED': StackState.CHECK_FAILED}

    @classmethod
    def from_stack_details_json(cls, stack_json):
        action, status = stack_json['stack_status'].split('_', 1)

        return cls(id=stack_json['id'],
                   name=stack_json['stack_name'],
                   action=action,
                   status=status)

    def get_state(self):
        if self.action == 'DELETE':
            return self.delete_states.get(self.status, StackState.OTHER)

        if (self.status == 'IN_PROGRESS' and
                self.action in ('CREATE', 'UPDATE', 'CHECK')):
            return StackState.IN_PROGRESS

        if self.action == 'CREATE' or self.action == 'UPDATE':
            return self.create_update_states.get(self.status, StackState.OTHER)

        if self.action == 'CHECK':
            return self.check_states.get(self.status, StackState.OTHER)

        return StackState.OTHER


def get_stack_tag_for_group(group_id):
    return "autoscale_%s" % group_id


def group_id_from_metadata(metadata):
    """
    Get the group ID of a server based on the metadata.

    The old key was ``rax:auto_scaling_group_id``, but the new key is
    ``rax:autoscale:group:id``.  Try pulling from the new key first, and
    if it doesn't exist, pull from the old.
    """
    return metadata.get(
        "rax:autoscale:group:id",
        metadata.get("rax:auto_scaling_group_id", None))


def generate_metadata(group_id, lb_descriptions):
    """
    Generate autoscale-specific Nova server metadata given the group ID and
    an iterable of :class:`ILBDescription` providers.

    :return: a metadata `dict` containing the group ID and LB information
    """
    metadata = {
        'rax:auto_scaling_group_id': group_id,
        'rax:autoscale:group:id': group_id
    }

    descriptions = groupby(lambda desc: (desc.lb_id, type(desc)),
                           lb_descriptions)

    for (lb_id, desc_type), descs in descriptions.iteritems():
        if desc_type == CLBDescription:
            key = 'rax:autoscale:lb:CloudLoadBalancer:{0}'.format(lb_id)
            metadata[key] = json.dumps([
                {'port': desc.port} for desc in descs])
        elif desc_type == RCv3Description:
            metadata['rax:autoscale:lb:RackConnectV3:{0}'.format(lb_id)] = ""

    return metadata


@attributes(['server_config', 'capacity',
             Attribute('desired_lbs', default_factory=pset, instance_of=PSet),
             Attribute('draining_timeout', default_value=0.0,
                       instance_of=float)])
class DesiredServerGroupState(object):
    """
    The desired state for a server scaling group.

    :ivar dict server_config: compute/nova part of the group launch config.
    :ivar int capacity: the number of desired servers within the group.
    :ivar dict desired_lbs: A mapping of load balancer IDs to lists of
        :class:`CLBDescription` instances.
    :ivar float draining_timeout: If greater than zero, when the server is
        scaled down it will be put into draining condition.  It will remain
        in draining condition for a maximum of ``draining_timeout`` seconds
        before being removed from the load balancer and then deleted.
    """
    def __init__(self):
        """
        Make attributes immutable.
        """
        self.server_config = freeze(self.server_config)


@attributes(['stack_config', 'capacity'])
class DesiredStackGroupState(object):
    """
    The desired state for a stack scaling group.

    :ivar dict stack_config: stack part of the group launch config.
    :ivar int capacity: the number of desired stack within the group.
    """
    def __init__(self):
        """
        Make attributes immutable.
        """
        self.stack_config = freeze(self.stack_config)


class ILBDescription(Interface):
    """
    A description of how to create a node on a load balancing entity.

    A load balancing entity can be a cloud load balancer or some kind of load
    balancer pool - anything that load balances.

    Implementers should have immutable attributes.
    """
    lb_id = IAttribute("The ID of this node.")

    def equivalent_definition(other_description):  # pragma: no cover
        """
        Check whether two description have the same definitions.

        A definition is anything non-server specific information that describes
        how to add a node to a particular load balancing entity.  For instance,
        the type of load balancer, the load balancer ID, and/or the port.

        :param ILBDescription other_description: the other description to
            compare against
        :return: whether the definitions are equivalent
        :rtype: `bool`
        """


class ILBNode(Interface):
    """
    A node, which is a mapping between a server and a :class:`ILBDescription`.

    :ivar ILBDescription description: The description of how the server is
        mapped to the load balancer.
    :ivar str node_id: The ID of the node, which is represents a unique
        mapping of a server to a load balancer (possibly one of many).
    """
    node_id = IAttribute("The ID of this node.")
    description = IAttribute("The LB Description for how this server is "
                             "attached to the load balancer.")

    def matches(server):  # pragma: no cover
        """
        Whether the server corresponds to this LB Node.

        :param server: The server to match against.
        :type server: :class:`NovaServer`

        :return: ``True`` if the server could match this LB node,
            ``False`` else
        :rtype: `bool`
        """

    def is_active():  # pragma: no cover
        """
        :return: Whether this node is currently active or enabled on the load
            balancer
        :rtype: `bool`
        """


class IDrainable(Interface):
    """
    The drainability part of a LB Node.  If a node is drainable, it should
    also provide this interface.
    """
    def currently_draining():  # pragma: no cover
        """
        :return: Whether this node currently in (load balancer) draining mode.
        :rtype: `bool`
        """

    def is_done_draining(now, timeout):  # pragma: no cover
        """
        Given the current time and the draining timeout, is the period of time
        the node must remain in draining over?

        :return: Whether the node is done draining.
        :rtype: `bool`
        :raises: ``DrainingUnavailable`` if draining info is not available
        """


@implementer(ILBDescription)
@attributes([Attribute("lb_id", instance_of=basestring),
             Attribute("port", instance_of=int),
             Attribute("weight", default_value=1, instance_of=int),
             Attribute("condition", default_value=CLBNodeCondition.ENABLED,
                       instance_of=NamedConstant),
             Attribute("type", default_value=CLBNodeType.PRIMARY,
                       instance_of=NamedConstant)])
class CLBDescription(object):
    """
    Information representing a Rackspace CLB port mapping; how a particular
    server *should* be port-mapped to a Rackspace Cloud Load Balancer.

    :ivar int lb_id: The Load Balancer ID.
    :ivar int port: The port, which together with the server's IP, specifies
        the service that should be load-balanced by the load balancer.
    :ivar int weight: The weight to be used for certain load-balancing
        algorithms if configured on the load balancer.  Defaults to 1,
        the max is 100.

    :ivar condition: One of ``ENABLED``, ``DISABLED``, or ``DRAINING`` -
        the default is ``ENABLED``
    :type condition: A member of :class:`CLBNodeCondition`

    :ivar type: One of ``PRIMARY`` or ``SECONDARY`` - default is ``PRIMARY``
    :type type: A member of :class:`CLBNodeType`
    """
    def equivalent_definition(self, other_description):
        """
        Whether the other description is also a :class:`CLBDescription` and
        whether it has the same load balancer ID and port.

        See :func:`ILBDescription.equivalent_definition`.
        """
        return (isinstance(other_description, CLBDescription) and
                other_description.lb_id == self.lb_id and
                other_description.port == self.port)


@attr.s
class CLB(object):
    """
    Cloud load balancer
    """
    # Is health monitor enabled?
    health_monitor = attr.ib(default=False)


@attr.s
class DrainingUnavailable(Exception):
    """
    Exception raised when draining info is required but is not available
    """
    lb_id = attr.ib()
    node_id = attr.ib()


@implementer(ILBNode, IDrainable)
@attr.s
class CLBNode(object):
    """
    A Rackspace Cloud Load Balancer node.

    :ivar str node_id: The ID of the node, which is represents a unique
        combination of IP and port number, on the CLB.  Also, see
        :obj:`ILBNode.node_id`.
    :ivar description: The description of how the node should be set up. See
        :obj:`ILBNode.description`.
    :type description: :class:`CLBescription`
    :ivar str address: The IP address of the node.  The IP and port form a
        unique mapping on the CLB, which is assigned a node ID.  Two
        nodes with the same IP and port cannot exist on a single CLB.
    :ivar float _drained_at: Seconds since EPOCH at which this node was put in
        DRAINING. This also represnts the time at which the node was created
        for a node that was created in DRAINING. Should be None if node is not
        DRAINING or when this info is not available.
    :ivar bool is_online: Is this node ONLINE and receiving traffic? This field
        corresponds to node's `status` field.
    :ivar int connections: The number of active connections on the node - this
        is None by default (the stat is not available yet).
    """
    node_id = attr.ib(validator=instance_of(basestring))
    description = attr.ib(validator=instance_of(CLBDescription))
    address = attr.ib(validator=instance_of(basestring))
    _drained_at = attr.ib(validator=optional(instance_of(float)), default=None)
    is_online = attr.ib(validator=optional(instance_of(bool)), default=True)
    connections = attr.ib(default=None)

    @property
    def drained_at(self):
        """
        Return when this node was drained.

        :return: Seconds since EPOCH
        :rtype: float
        :raises: :obj:`DrainingUnavailable` if this info is not available
        """
        if self._drained_at is None:
            raise DrainingUnavailable(self.description.lb_id, self.node_id)
        return self._drained_at

    @drained_at.setter
    def drained_at(self, updated):
        """
        Update the internal _drained_at value

        :param float updated: The updated value as seconds since EPOCH
        """
        self._drained_at = updated

    def matches(self, server):
        """
        See :func:`ILBNode.matches`.
        """
        return (isinstance(server, NovaServer) and
                server.servicenet_address == self.address)

    def currently_draining(self):
        """
        See :func:`IDrainable.currently_draining`.
        """
        return self.description.condition == CLBNodeCondition.DRAINING

    def is_done_draining(self, now, timeout):
        """
        See :func:`IDrainable.is_done_draining`.
        """
        return now - self.drained_at >= timeout or self.connections == 0

    def is_active(self):
        """
        See :func:`ILBNode.is_active`.
        """
        return self.description.condition != CLBNodeCondition.DISABLED

    @classmethod
    def from_node_json(cls, lb_id, json):
        """
        Create an instance of this class based on node JSON data from the CLB
        API.
        """
        return cls(
            node_id=str(json['id']),
            address=json['address'],
            is_online=(json["status"] == "ONLINE"),
            description=CLBDescription(
                lb_id=str(lb_id),
                port=json['port'],
                weight=json.get('weight', 1),
                condition=CLBNodeCondition.lookupByName(json['condition']),
                type=CLBNodeType.lookupByName(json['type'])))


@implementer(ILBDescription)
@attributes([Attribute("lb_id", instance_of=basestring)])
class RCv3Description(object):
    """
    Information representing a RackConnect V3/server mapping: how a particular
    server *should* be added a RackConnect V3 load balancer pool.

    RackConnect V3 nodes aren't really configurable, so only has the load
    balancer ID.

    :ivar int lb_id: The Load Balancer ID.
    """
    def equivalent_definition(self, other_description):
        """
        Given that no customization is available, is the same as testing
        equivalence.

        See :func:`ILBDescription.equivalent_definition`.
        """
        return self == other_description


@implementer(ILBNode)
@attributes([Attribute("node_id", instance_of=basestring),
             Attribute("description", instance_of=RCv3Description),
             Attribute("cloud_server_id", instance_of=basestring)])
class RCv3Node(object):
    """
    A RackConnect V3 node.

    :ivar str node_id: See :obj:`ILBNode.node_id`.
    :ivar description: See :obj:`ILBNode.description`.
    :type description: :class:`RCv3Description`

    :ivar str cloud_server_id: The ID of the cloud server represented by this
        node
    """
    def matches(self, server):
        """
        See :func:`ILBNode.matches`.
        """
        return (isinstance(server, NovaServer) and
                server.id == self.cloud_server_id)
