"""Constants."""

from twisted.python.constants import Names, NamedConstant


class ServiceType(Names):
    """Constants representing Rackspace cloud services."""
    CLOUD_SERVERS = NamedConstant()
    CLOUD_LOAD_BALANCERS = NamedConstant()
    RACKCONNECT_V3 = NamedConstant()


def get_service_mapping(get_service_name):
    """
    Return a mapping of :class:`ServiceType` members to the actual configured
    service names to look up in tenant catalogs.

    :param service_config: function of idiomatic service name ->
        deployment-specific service name
    """
    return {
        ServiceType.CLOUD_SERVERS: get_service_name('cloudServersOpenStack'),
        ServiceType.CLOUD_LOAD_BALANCERS: get_service_name("cloudLoadBalancers"),
        ServiceType.RACKCONNECT_V3: get_service_name('rackconnect'),
    }
