"""
Code for composing all of the convergence functionality together.
"""
import json

from pyrsistent import freeze, pset

from toolz.dicttoolz import keyfilter
from toolz.itertoolz import groupby

from otter.convergence.model import CLBDescription, DesiredGroupState


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

    NOTE: Currently ignores RackConnectV3 configs. Will add them when it gets
    implemented in convergence
    """
    return pset([
        CLBDescription(lb_id=str(lb['loadBalancerId']), port=lb['port'])
        for lb in lbs_json if lb.get('type') != 'RackConnectV3'])


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
    lbs = freeze(launch_config['args'].get('loadBalancers', []))
    server_lc = prepare_server_launch_config(
        group_id,
        freeze({'server': launch_config['args']['server']}),
        lbs)
    lbs = json_to_LBConfigs(lbs)
    desired_state = DesiredGroupState(
        server_config=server_lc,
        capacity=desired, desired_lbs=lbs)
    return desired_state


def _sanitize_lb_metadata(lb_config_json):
    """
    Takes load balancer config json, as from :obj:`otter.json_schema._clb_lb`
    and :obj:`otter.json_schema._rcv3_lb` and normalizes it.
    """
    sanitized = keyfilter(lambda k: k in ('type', 'port'), lb_config_json)
    # provide a default type
    sanitized.setdefault('type', 'CloudLoadBalancer')
    return sanitized


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

    lbs = groupby(lambda conf: conf['loadBalancerId'], lb_args)

    for lb_id in lbs:
        configs = [_sanitize_lb_metadata(config) for config in lbs[lb_id]
                   if config.get('type') != 'RackConnectV3']

        server_config = server_config.set_in(
            ('server', 'metadata', 'rax:autoscale:lb:{0}'.format(lb_id)),
            json.dumps(configs))

    return server_config
