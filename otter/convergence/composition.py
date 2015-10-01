"""
Code for composing all of the convergence functionality together.
"""
from pyrsistent import freeze, pset

from toolz.dicttoolz import get_in, merge
from toolz.itertoolz import groupby

from otter.convergence.model import (
    CLBDescription,
    DesiredServerGroupState,
    DesiredStackGroupState,
    RCv3Description,
    generate_metadata,
    get_stack_tag_for_group)
from otter.util.fp import set_in


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

    :param lbs_json: Sequence of load balancer configs
    :return: Sequence of :class:`ILBDescription` providers
    """
    by_type = groupby(lambda lb: lb.get('type', 'CloudLoadBalancer'), lbs_json)
    return pset(
        [CLBDescription(lb_id=str(lb['loadBalancerId']), port=lb['port'])
         for lb in by_type.get('CloudLoadBalancer', [])] +
        [RCv3Description(lb_id=str(lb['loadBalancerId']))
         for lb in by_type.get('RackConnectV3', [])]
    )


def get_desired_server_group_state(group_id, launch_config, desired):
    """
    Create a :obj:`DesiredServerGroupState` from a group details.

    :param str group_id: The group ID
    :param dict launch_config: Group's launch config as per
        :obj:`otter.json_schema.group_schemas.launch_config`
    :param int desired: Group's desired capacity
    """
    lbs = freeze(launch_config['args'].get('loadBalancers', []))
    lbs = json_to_LBConfigs(lbs)
    server_lc = prepare_server_launch_config(
        group_id,
        freeze({'server': launch_config['args']['server']}),
        lbs)
    draining = float(launch_config["args"].get("draining_timeout", 0.0))
    desired_state = DesiredServerGroupState(
        server_config=server_lc,
        capacity=desired, desired_lbs=lbs,
        draining_timeout=draining)
    return desired_state


def get_desired_stack_group_state(group_id, launch_config, desired):
    """
    Create a :obj:`DesiredStackGroupState` from a group details.

    :param str group_id: The group ID
    :param dict launch_config: Group's launch_stack config as per
        :obj:`otter.json_schema.group_schemas.launch_config`
    :param int desired: Group's desired capacity
    """

    stack_lc = prepare_stack_launch_config(
        group_id, freeze(launch_config['args']['stack']))

    desired_state = DesiredStackGroupState(stack_config=stack_lc,
                                           capacity=desired)
    return desired_state


def prepare_server_launch_config(group_id, server_config, lb_descriptions):
    """
    Prepare a server config (the server part of the Group's launch config)
    with any necessary dynamic data.

    :param str group_id: The group ID
    :param PMap server_config: The server part of the Group's launch config,
        as per :obj:`otter.json_schema.group_schemas.server` except as the
        value of a one-element PMap with key "server".
    :param iterable lb_descriptions: iterable of
        :class:`ILBDescription` providers
    """
    updated_metadata = merge(
        get_in(('server', 'metadata'), server_config, {}),
        generate_metadata(group_id, lb_descriptions))

    return set_in(server_config, ('server', 'metadata'), updated_metadata)


def prepare_stack_launch_config(group_id, stack_config):
    """
    Prepare a stack config (the stack part of the Group's launch config)
    with any necessary dynamic data.

    :param str group_id: The group ID
    :param PMap stack_config: The stack part of the Group's launch config,
        as per :obj:`otter.json_schema.group_schemas.stack`.
    """
    # Set stack name and tag to the same thing
    stack_config = set_in(stack_config, ('stack_name',),
                          get_stack_tag_for_group(group_id))
    stack_config = set_in(stack_config, ('tags',),
                          get_stack_tag_for_group(group_id))
    return stack_config
