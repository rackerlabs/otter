"""
Data classes for representing bits of information that need to share a
representation across the different phases of convergence.
"""

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
