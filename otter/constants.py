"""Constants."""

from twisted.python.constants import NamedConstant, Names


LOCK_PATH = '/locks'


class ServiceType(Names):
    """Constants representing Rackspace cloud services."""
    CLOUD_SERVERS = NamedConstant()
    CLOUD_LOAD_BALANCERS = NamedConstant()
    RACKCONNECT_V3 = NamedConstant()
    CLOUD_METRICS_INGEST = NamedConstant()


def get_service_configs(config):
    """
    Return service configurations for all services based on the config data.

    Returns a dict, where keys are :obj:`ServiceType` members, and values are
    service configs. A service config is a dict with ``name`` and ``region``
    keys.

    :param dict config: Config from file containing service names that will be
        there in service catalog
    """
    return {
        ServiceType.CLOUD_SERVERS: {
            'name': config['cloudServersOpenStack'],
            'region': config['region'],
        },
        ServiceType.CLOUD_LOAD_BALANCERS: {
            'name': config['cloudLoadBalancers'],
            'region': config['region'],
        },
        ServiceType.RACKCONNECT_V3: {
            'name': config['rackconnect'],
            'region': config['region'],
        },
        ServiceType.CLOUD_METRICS_INGEST: {
            'name': config['metrics']['service'],
            'region': config['metrics']['region'],
        },
    }
