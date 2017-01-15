"""Constants."""

from twisted.python.constants import NamedConstant, Names


CONVERGENCE_DIRTY_DIR = '/groups/divergent'
CONVERGENCE_PARTITIONER_PATH = '/convergence-partitioner'


class ServiceType(Names):
    """
    Constants representing Rackspace cloud services.

    Note: CLOUD_FEEDS_CAP represents customer access policy events which like
    CLOUD_FEEDS is fixed URL but different from CLOUD_FEEDS.
    """
    CLOUD_SERVERS = NamedConstant()
    CLOUD_LOAD_BALANCERS = NamedConstant()
    RACKCONNECT_V3 = NamedConstant()
    CLOUD_METRICS_INGEST = NamedConstant()
    CLOUD_FEEDS = NamedConstant()
    CLOUD_FEEDS_CAP = NamedConstant()
    CLOUD_ORCHESTRATION = NamedConstant()


def get_service_configs(config):
    """
    Return service configurations for all services based on the config data.

    Returns a dict, where keys are :obj:`ServiceType` members, and values are
    service configs. A service config is a dict with ``name`` and ``region``
    keys.

    :param dict config: Config from file containing service names that will be
        there in service catalog
    """
    region = config['region']
    configs = {
        ServiceType.CLOUD_SERVERS: {
            'name': config['cloudServersOpenStack'],
            'region': region,
        },
        ServiceType.CLOUD_LOAD_BALANCERS: {
            'name': config['cloudLoadBalancers'],
            'region': region,
        },
        ServiceType.CLOUD_ORCHESTRATION: {
            'name': config['cloudOrchestration'],
            'region': region,
        },
        ServiceType.RACKCONNECT_V3: {
            'name': config['rackconnect'],
            'region': region,
        }
    }

    metrics = config.get('metrics')
    if metrics is not None:
        configs[ServiceType.CLOUD_METRICS_INGEST] = {
            'name': metrics['service'], 'region': metrics['region']}

    # {"cloudfeeds"...} contains config for 2 feeds services: One where otter
    # pushes scaling group events `otter.log.cloudfeeds` as {"url": ...}
    # and other where it fetches customer access events for terminator which
    # is {"customer_access_events": {"url": "https://url"} or
    #                               {"name": "service name"}}
    # The {"name"..} option is to test otter against mimic that only returns
    # URLs from service catalog.
    cf = config.get('cloudfeeds')
    if cf is not None:
        configs[ServiceType.CLOUD_FEEDS] = {'url': cf['url']}
        cap_conf = cf.get("customer_access_events")
        if cap_conf is not None:
            if "url" in cap_conf:
                cap_service_conf = {"url": cap_conf["url"]}
            else:
                cap_service_conf = {"name": cap_conf["name"], "region": region}
            configs[ServiceType.CLOUD_FEEDS_CAP] = cap_service_conf

    return configs
