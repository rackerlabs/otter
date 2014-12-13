"""
Code for composing all of the convergence functionality together.
"""

from operator import itemgetter
import time

from effect import parallel

from toolz.curried import map

from otter.convergence.effecting import _reqs_to_effect
from otter.convergence.gathering import (
    get_load_balancer_contents,
    get_scaling_group_servers,
    json_to_LBConfigs,
    to_nova_server)
from otter.convergence.model import DesiredGroupState
from otter.convergence.planning import converge, optimize_steps


def execute_convergence(request_func, group_id, desired, launch_config,
                        get_servers=get_scaling_group_servers,
                        get_lb=get_load_balancer_contents):
    """
    Execute convergence. This function will do following:
    1. Get state of the nova, CLB and RCv3.
    2. Call `converge` with above info and get steps to execute
    3. Execute these steps
    This is in effect single cycle execution. A layer above this is expected
    to keep calling this until this function returns False

    :param request_func: Tenant bound request function
    :param bytes group_id: Tenant's group
    :param int desired: Group's desired capacity
    :param dict launch_config: Group's launch config as per
                              :obj:`otter.json_schema.group_schemas.launch_config`
    :param callable get_servers: Optional arg to get scaling group servers useful for testing
    :param callable get_lb: Optional arg to get load balancer info useful for testing

    :return: Effect with Bool specifying if it should be called again
    :rtype: :class:`effect.Effect`
    """
    eff = parallel(
        [get_servers(request_func).on(itemgetter(group_id)).on(map(to_nova_server)),
         get_lb(request_func)])

    lbs = json_to_LBConfigs(launch_config['args']['loadBalancers'])
    desired_state = DesiredGroupState(launch_config={'server': launch_config['args']['server']},
                                      desired=desired, desired_lbs=lbs)

    conv_eff = eff.on(lambda (servers, lb_nodes): converge(desired_state, servers, lb_nodes,
                                                           time.time()))
    # TODO: Do request specific throttling. For ex create only 3 servers at a time
    return conv_eff.on(optimize_steps).on(
        lambda steps: _reqs_to_effect(request_func, [s.as_request() for s in steps])).on(bool)


def tenant_is_enabled(tenant_id, get_config_value):
    """
    Feature-flag test: is the given tenant enabled for convergence?

    :param str tenant_id: A tenant's ID, which may or may not be present in the
        "convergence-tenants" portion of the configuration file.
    :param callable get_config_value: config key -> config value.
    """
    enabled_tenant_ids = get_config_value("convergence-tenants")
    return (tenant_id in enabled_tenant_ids)
