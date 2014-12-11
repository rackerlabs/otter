"""
Data classes for representing bits of information that need to share a
representation across the different phases of convergence.
"""

from characteristic import attributes, Attribute

from pyrsistent import freeze

from twisted.python.constants import Names, NamedConstant



class NodeCondition(Names):
    """Constants representing the condition a load balancer node can be in"""
    ENABLED = NamedConstant()   # Node can accept new connections.
    DRAINING = NamedConstant()  # Node cannot accept any new connections.
                                # Existing connections are forcibly terminated.
    DISABLED = NamedConstant()  # Node cannot accept any new connections.
                                # Existing connections are permitted to continue.


class NodeType(Names):
    """Constants representing the type of a load balancer node"""
    PRIMARY = NamedConstant()    # Node in normal rotation
    SECONDARY = NamedConstant()  # Node only put into normal rotation if a
                                 # primary node fails.


class ServerState(Names):
    """Constants representing the state cloud servers can have"""
    ACTIVE = NamedConstant()    # corresponds to Nova "ACTIVE"
    ERROR = NamedConstant()     # corresponds to Nova "ERROR"
    BUILD = NamedConstant()     # corresponds to Nova "BUILD" or "BUILDING"
    DRAINING = NamedConstant()  # Autoscale is deleting the server


@attributes(["lb_id", "node_id", "address",
             Attribute("drained_at", default_value=0.0, instance_of=float),
             Attribute("connections", default_value=None),
             "config"])
class LBNode(object):
    """
    Information representing an actual node on a load balancer, which is
    an actual, existing, specific port mapping on a load balancer.

    :ivar int lb_id: The Load Balancer ID.
    :ivar int node_id: The ID of the node, which is represents a unique
        combination of IP and port number, on the load balancer.
    :ivar str address: The IP address of the node.  The IP and port form a
        unique mapping on the load balancer, which is assigned a node ID.  Two
        nodes with the same IP and port cannot exist on a single load balancer.
    :ivar float drained_at: EPOCH at which this node was put in DRAINING.
        Will be 0 if node is not DRAINING
    :ivar int connections: The number of active connections on the node - this
        is None by default (the stat is not available yet)

    :ivar config: The configuration for the port mapping
    :type config: :class:`LBConfig`
    """


@attributes(["port",
             Attribute("weight", default_value=1, instance_of=int),
             Attribute("condition", default_value=NodeCondition.ENABLED,
                       instance_of=NamedConstant),
             Attribute("type", default_value=NodeType.PRIMARY,
                       instance_of=NamedConstant)])
class LBConfig(object):
    """
    Information representing a load balancer port mapping; how a particular
    server *should* be port-mapped to a load balancer.

    :ivar int port: The port, which together with the server's IP, specifies
        the service that should be load-balanced by the load balancer.
    :ivar int weight: The weight to be used for certain load-balancing
        algorithms if configured on the load balancer.  Defaults to 1,
        the max is 100.
    :ivar str condition: One of ``ENABLED``, ``DISABLED``, or ``DRAINING`` -
        the default is ``ENABLED``
    :ivar str type: One of ``PRIMARY`` or ``SECONDARY`` - default is ``PRIMARY``
    """


@attributes(['id', 'state', 'created',
             Attribute('servicenet_address', default_value='', instance_of=str)])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    :ivar str servicenet_address: The private ServiceNet IPv4 address, if
        the server is on the ServiceNet network
    """


@attributes(['launch_config', 'desired',
             Attribute('desired_lbs', default_factory=dict, instance_of=dict),
             Attribute('draining_timeout', default_value=0.0, instance_of=float)])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    :ivar dict desired_lbs: A mapping of load balancer IDs to lists of
        :class:`LBConfig` instances.
    :ivar float draining_timeout: If greater than zero, when the server is
        scaled down it will be put into draining condition.  It will remain
        in draining condition for a maximum of ``draining_timeout`` seconds
        before being removed from the load balancer and then deleted.
    """

    def __init__(self):
        self.launch_config = freeze(self.launch_config)


