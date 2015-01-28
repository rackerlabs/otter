"""
Code for composing all of the convergence functionality together.
"""
import json
import time

from collections import defaultdict

from pyrsistent import freeze

from toolz.dicttoolz import keyfilter

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
    if enabled_tenant_ids is not None:
        return (tenant_id in enabled_tenant_ids)
    return False


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
    return dict(lbd)


def get_desired_group_state(group_id, launch_config, desired):
    """
    Create a :obj:`DesiredGroupState` from a group details.

    :param str group_id: The group ID
    :param dict launch_config: Group's launch config as per
        :obj:`otter.json_schema.group_schemas.launch_config`
    :param int desired: Group's desired capacity

    NOTE: Currently this ignores draining timeout settings, since it has
    not been added to any schema yet.
    """
    lbs = launch_config['args'].get('loadBalancers', [])
    server_lc = prepare_server_launch_config(
        group_id,
        freeze({'server': launch_config['args']['server']}),
        freeze(lbs))
    lbs = json_to_LBConfigs(lbs)
    desired_state = DesiredGroupState(
        server_config=server_lc,
        capacity=desired, desired_lbs=lbs)
    return desired_state


def prepare_server_launch_config(group_id, server_config, lb_args):
    """
    Prepares a server config (the server part of the Group's launch config)
    with any necessary dynamic data.

    :param str group_id: The group ID
    :param PMap server_config: The server part of the Group's launch config,
        as per :obj:`otter.json_schema.group_schemas.server` except as the
        value of a one-element PMap with key "server".
    :param PMap lb_args: The load balancer part of the Group's launch_config

    This function assumes that `lb_args` is mostly well-formed data, and is
    not missing any data, since it should have been sanitized before getting
    to this point.

    NOTE: Currently this ignores RCv3 settings and draining timeout settings,
    since they haven't been implemented yet.
    """
    server_config = server_config.set_in(
        ('server', 'metadata', 'rax:auto_scaling_group_id'), group_id)

    for config in lb_args:
        if config.get('type') != 'RackConnectV3':
            sanitized = keyfilter(lambda k: k in ('type', 'port'), config)
            # provide a default type
            sanitized.setdefault('type', 'CloudLoadBalancer')

            server_config = server_config.set_in(
                ('server', 'metadata',
                 'rax:autoscale:lb:{0}'.format(config['loadBalancerId'])),
                json.dumps(sanitized))

    return server_config
