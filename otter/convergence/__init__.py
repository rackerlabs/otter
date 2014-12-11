# -*- test-case-name: otter.test.test_convergence -*-
"""
Convergence.
"""

from itertools import izip as zip
from operator import itemgetter
import time
from collections import defaultdict

from characteristic import attributes, Attribute
from effect import parallel
from pyrsistent import pbag, freeze, s, pset
from zope.interface import Interface, implementer

from twisted.python.constants import Names, NamedConstant

from effect import parallel

from toolz.curried import filter, groupby, map
from toolz.functoolz import compose, identity
from toolz.itertoolz import concat, concatv, mapcat
from toolz.dicttoolz import get_in

from otter.constants import ServiceType
from otter.util.http import append_segments
from otter.util.fp import partition_bool, partition_groups
from otter.util.timestamp import timestamp_to_epoch

# radix in-development imports

from otter.convergence.planning import converge, _remove_from_lb_with_draining, _converge_lb_state
from otter.convergence.steps import AddNodesToLoadBalancer, BulkAddToRCv3, BulkRemoveFromRCv3, CreateServer, DeleteServer, RemoveFromLoadBalancer, ChangeLoadBalancerNode, SetMetadataItemOnServer, Request, Convergence
from otter.convergence.model import NodeCondition, NodeType, ServerState, LBNode, LBConfig
from otter.convergence.gathering import get_all_server_details, get_scaling_group_servers, get_load_balancer_contents, extract_drained_at



def to_nova_server(server_json):
    """
    Convert from JSON format to :obj:`NovaServer` instance
    """
    ips = get_in(['addresses', 'private'], server_json, default=[])
    ip = ''
    if len(ips) > 0:
        ip = [addr['addr'] for addr in ips if addr['version'] == 4][0]
    return NovaServer(id=server_json['id'], state=ServerState.lookupByName(server_json['state']),
                      created=timestamp_to_epoch(server_json['created']),
                      servicenet_address=ip)


@attributes(['launch_config', 'desired',
             Attribute('desired_lbs', default_factory=dict, instance_of=dict),
             Attribute('draining_timeout', default_value=0.0, instance_of=float)])
class DesiredGroupState(object):
    """
    The desired state for a scaling group.

    :ivar dict launch_config: nova launch config.
    :ivar int desired: the number of desired servers within the group.
    :ivar dict desired_lbs: A mapping of load balancer IDs to lists of
        :class:`LBConfig` instances.
    :ivar float draining_timeout: If greater than zero, when the server is
        scaled down it will be put into draining condition.  It will remain
        in draining condition for a maximum of ``draining_timeout`` seconds
        before being removed from the load balancer and then deleted.
    """

    def __init__(self):
        self.launch_config = freeze(self.launch_config)


@attributes(['id', 'state', 'created',
             Attribute('servicenet_address', default_value='', instance_of=str)])
class NovaServer(object):
    """
    Information about a server that was retrieved from Nova.

    :ivar str id: The server id.
    :ivar str state: Current state of the server.
    :ivar float created: Timestamp at which the server was created.
    :ivar str servicenet_address: The private ServiceNet IPv4 address, if
        the server is on the ServiceNet network
    """


_optimizers = {}


def _optimizer(step_type):
    """
    A decorator for a type-specific optimizer.

    Usage::

        @_optimizer(StepTypeToOptimize)
        def optimizing_function(steps_of_that_type):
           return iterable_of_optimized_steps
    """
    def _add_to_optimizers(optimizer):
        _optimizers[step_type] = optimizer
        return optimizer
    return _add_to_optimizers


@_optimizer(AddNodesToLoadBalancer)
def _optimize_lb_adds(lb_add_steps):
    """
    Merge together multiple :obj:`AddNodesToLoadBalancer`, per load balancer.

    :param steps_by_lb: Iterable of :obj:`AddNodesToLoadBalancer`.
    """
    steps_by_lb = groupby(lambda s: s.lb_id, lb_add_steps)
    return [
        AddNodesToLoadBalancer(
            lb_id=lbid,
            address_configs=pset(reduce(lambda s, y: s.union(y),
                                        [step.address_configs for step in steps])))
        for lbid, steps in steps_by_lb.iteritems()
    ]


def optimize_steps(steps):
    """
    Optimize steps.

    Currently only optimizes per step type. See the :func:`_optimizer`
    decorator for more information on how to register an optimizer.

    :param pbag steps: Collection of steps.
    :return: a pbag of steps.
    """
    def grouping_fn(step):
        step_type = type(step)
        if step_type in _optimizers:
            return step_type
        else:
            return "unoptimizable"

    steps_by_type = groupby(grouping_fn, steps)
    unoptimizable = steps_by_type.pop("unoptimizable", [])
    omg_optimized = concat(_optimizers[step_type](steps)
                           for step_type, steps in steps_by_type.iteritems())
    return pbag(concatv(omg_optimized, unoptimizable))


def _reqs_to_effect(request_func, conv_requests):
    """Turns a collection of :class:`Request` objects into an effect.

    :param request_func: A pure-http request function, as produced by
        :func:`otter.http.get_request_func`.
    :param conv_requests: Convergence requests to turn into effects.
    :return: An effect which will perform all the requests in parallel.
    :rtype: :class:`Effect`
    """
    effects = [request_func(service_type=r.service,
                            method=r.method,
                            url=r.path,
                            headers=r.headers,
                            data=r.data,
                            success_codes=r.success_codes)
               for r in conv_requests]
    return parallel(effects)


def json_to_LBConfigs(lbs_json):
    """
    Convert load balancer config from JSON to :obj:`LBConfig`

    :param list lbs_json: List of load balancer configs
    :return: `dict` of LBid -> [LBConfig] mapping

    NOTE: Currently ignores RackConnectV3 configs. Will add them when it gets
    implemented in convergence
    """
    lbd = defaultdict(list)
    for lb in lbs_json:
        if lb.get('type') != 'RackConnectV3':
            lbd[lb['loadBalancerId']].append(LBConfig(port=lb['port']))
    return lbd


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
    return conv_eff.on(lambda c: optimize_steps(c.steps)).on(
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
