"""
Data classes for representing bits of information that need to share a
representation across the different phases of convergence.
"""

from characteristic import Attribute, attributes

from pyrsistent import PMap, freeze, pmap

from twisted.python.constants import NamedConstant, Names

from zope.interface import Attribute as IAttribute, Interface, implementer


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
    """

    ACTIVE = NamedConstant()
    """
    Corresponds to Nova's ``ACTIVE`` state.
    """

    ERROR = NamedConstant()
    """
    Corresponds to Nova's ``ERROR`` state.
    """

    BUILD = NamedConstant()
    """
    Corresponds to Nova's ``BUILD`` and ``BUILDING`` states.
    """

    DRAINING = NamedConstant()
    """"
    Autoscale is deleting the server.
    """


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

    FAILURE = NamedConstant()
    """
    The step failed. Retrying convergence won't help.
    """


@attributes(['id', 'state', 'created', 'image_id', 'flavor_id',
             Attribute('desired_lbs', default_factory=pmap, instance_of=PMap),
             Attribute('servicenet_address',
                       default_value='',
                       instance_of=basestring)])
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

    :ivar PMap desired_lbs: An immutable mapping of load balancer IDs to lists
        of :class:`CLBDescription` instances.
    """


@attributes(['server_config', 'capacity',
             Attribute('desired_lbs', default_factory=pmap, instance_of=PMap),
             Attribute('draining_timeout', default_value=0.0,
                       instance_of=float)])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

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


class ILBDescription(Interface):
    """
    A description of how to create a node on a load balancing entity.

    A load balancing entity can be a cloud load balancer or some kind of load
    balancer pool - anything that load balances.

    Implementers should have immutable attributes.
    """
    def equivalent_definition(other_description):  # pragma: no cover
        """
        Checks whether two description have the same definitions.

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

        :return: ``True`` if the server could match this LB node, ``False`` else
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
        """


@implementer(ILBDescription)
@attributes([Attribute("lb_id", instance_of=str),
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


@implementer(ILBNode, IDrainable)
@attributes([Attribute("node_id", instance_of=str),
             Attribute("description", instance_of=CLBDescription),
             Attribute("address", instance_of=str),
             Attribute("drained_at", default_value=0.0, instance_of=float),
             Attribute("connections", default_value=None)])
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
    :ivar float drained_at: EPOCH at which this node was put in DRAINING.
        Should be 0 if node is not DRAINING.
    :ivar int connections: The number of active connections on the node - this
        is None by default (the stat is not available yet).
    """
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
