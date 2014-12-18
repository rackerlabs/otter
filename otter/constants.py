"""Constants."""

from twisted.python.constants import Names, NamedConstant

from toolz.dicttoolz import get_in


class ServiceType(Names):
    """Constants representing Rackspace cloud services."""
    CLOUD_SERVERS = NamedConstant()
    CLOUD_LOAD_BALANCERS = NamedConstant()
    RACKCONNECT_V3 = NamedConstant()
    CLOUD_METRICS_INGEST = NamedConstant()


def get_service_mapping(config):
    """
    Return a mapping of :class:`ServiceType` members to the actual configured
    service names to look up in tenant catalogs.

    :param dict config: Config from file containing service names that will be
        there in service catalog
    """
    return {
        ServiceType.CLOUD_SERVERS: config['cloudServersOpenStack'],
        ServiceType.CLOUD_LOAD_BALANCERS: config["cloudLoadBalancers"],
        ServiceType.RACKCONNECT_V3: config['rackconnect'],
        ServiceType.CLOUD_METRICS_INGEST: config['metrics']['service']
    }
