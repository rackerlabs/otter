"""
Code for composing all of the convergence functionality together.
"""
import time

from collections import defaultdict

from pyrsistent import freeze

from otter.convergence.effecting import steps_to_effect
from otter.convergence.gathering import get_all_convergence_data
from otter.convergence.model import CLBDescription, DesiredGroupState
from otter.convergence.planning import plan


def execute_convergence(group_id, desired_group_state,
                        get_all_convergence_data=get_all_convergence_data):
    """
    Execute convergence. This function will do following:
    1. Get state of the nova, CLB and RCv3.
    2. Get a plan for convergence
    3. Return an Effect representing the execution of the steps in the plan.

    This is in effect single cycle execution. A layer above this is expected
    to keep calling this until this function returns False

    :param bytes group_id: Tenant's group
    :param DesiredGroupState desired_group_state: the desired state

    :return: Effect of bool specifying if the effect should be performed again
    :rtype: :class:`effect.Effect`
    """
    eff = get_all_convergence_data(group_id)
    conv_eff = eff.on(
        lambda (servers, lb_nodes): plan(desired_group_state, servers,
                                         lb_nodes, time.time()))
    return conv_eff.on(steps_to_effect).on(bool)


def tenant_is_enabled(tenant_id, get_config_value):
    """
    Feature-flag test: is the given tenant enabled for convergence?

    :param str tenant_id: A tenant's ID, which may or may not be present in the
        "convergence-tenants" portion of the configuration file.
    :param callable get_config_value: config key -> config value.
    """
    enabled_tenant_ids = get_config_value("convergence-tenants")
    return (tenant_id in enabled_tenant_ids)


def json_to_LBConfigs(lbs_json):
    """
    Convert load balancer config from JSON to :obj:`CLBDescription`

    :param list lbs_json: List of load balancer configs
    :return: `dict` of LBid -> [LBDescription] mapping

    NOTE: Currently ignores RackConnectV3 configs. Will add them when it gets
    implemented in convergence
    """
    lbd = defaultdict(list)
    for lb in lbs_json:
        if lb.get('type') != 'RackConnectV3':
            lbd[lb['loadBalancerId']].append(CLBDescription(
                lb_id=str(lb['loadBalancerId']), port=lb['port']))
    return lbd


def get_desired_group_state(group_id, launch_config, desired):
    """
    Create a :obj:`DesiredGroupState` from a group details.

    :param str group_id: The group ID
    :param dict launch_config: Group's launch config as per
        :obj:`otter.json_schema.group_schemas.launch_config`
    :param int desired: Group's desired capacity
    """
    server_lc = prepare_server_launch_config(
        group_id,
        freeze({'server': launch_config['args']['server']}))
    lbs = json_to_LBConfigs(launch_config['args']['loadBalancers'])
    desired_state = DesiredGroupState(
        launch_config=server_lc,
        capacity=desired, desired_lbs=lbs)
    return desired_state


def prepare_server_launch_config(group_id, launch_config):
    """Prepare a launch config with any necessary dynamic data."""
    return launch_config.set_in(
        ('server', 'metadata', 'rax:auto_scaling_group_id'),
        group_id)
