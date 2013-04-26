"""
Initial implementation of a version one launch_server_v1 config.

Ultimately this launch config will be responsible for:
0) Generating server name and injecting our AS metadata (TODO)
1) Starting a server
2) Executing a user defined deployment script (TODO)
3) Adding the server to a load balancer.
4) Configuring MaaS? (TODO)

The shape of this is nowhere near solidified, probably most of these
functions are actually private and many of the utilities will get
moved out of here.

Also no attempt is currently being made to define the public API for
initiating a launch_server job.
"""

import json
import itertools
from copy import deepcopy

from twisted.internet.defer import Deferred, gatherResults
from twisted.internet.task import LoopingCall

import treq

from otter.util.config import config_value
from otter.util.http import append_segments, headers, check_success
from otter.util.hashkey import generate_server_name


def server_details(server_endpoint, auth_token, server_id):
    """
    Fetch the details of a server as specified by id.

    :param str server_endpoint: A str base URI probably from the service
        catalog.

    :param str auth_token: The auth token.
    :param str server_id: The opaque ID of a server.

    :return: A dict of the server details.
    """
    d = treq.get(append_segments(server_endpoint, 'servers', server_id),
                 headers=headers(auth_token))
    d.addCallback(check_success, [200, 203])
    return d.addCallback(treq.json_content)


def wait_for_status(log,
                    server_endpoint,
                    auth_token,
                    server_id,
                    expected_status,
                    interval=5,
                    clock=None):
    """
    Wait until the server specified by server_id's status is expected_status.

    @TODO: Timeouts
    @TODO: Errback on error statuses.

    :param log: A bound logger.
    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth token.
    :param str server_id: Opaque nova server id.
    :param str expected_status: Nova status string.
    :param int interval: Polling interval.  Default: 5.

    :return: Deferred that fires when the expected status has been seen.
    """
    log.msg(format="Checking instance status every %(interval)s seconds",
            interval=interval)

    d = Deferred()

    def poll():
        def _check_status(server):
            log.msg(format="waiting for status %(expected_status)s got %(status)s",
                    expected_status=expected_status, status=server['server']['status'])
            if server['server']['status'] == expected_status:
                d.callback(server)

        sd = server_details(server_endpoint, auth_token, server_id)
        sd.addCallback(_check_status)

        return sd

    lc = LoopingCall(poll)

    if clock is not None:  # pragma: no cover
        lc.clock = clock

    def _stop(r):
        lc.stop()
        return r

    d.addCallback(_stop)

    return lc.start(interval).addCallback(lambda _: d)


def create_server(server_endpoint, auth_token, server_config):
    """
    Create a new server.

    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param dict server_config: Nova server config.

    :return: Deferred that fires with the CreateServer response as a dict.
    """
    d = treq.post(append_segments(server_endpoint, 'servers'),
                  headers=headers(auth_token),
                  data=json.dumps({'server': server_config}))
    d.addCallback(check_success, [202])
    return d.addCallback(treq.json_content)


def add_to_load_balancer(endpoint, auth_token, lb_config, ip_address):
    """
    Add an IP addressed to a load balancer based on the lb_config.

    TODO: Handle load balancer node metadata.

    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param str lb_config: An lb_config dictionary.
    :param str ip_address: The IP Address of the node to add to the load
        balancer.

    :return: Deferred that fires with the Add Node to load balancer response
        as a dict.
    """
    lb_id = lb_config['loadBalancerId']
    port = lb_config['port']
    path = append_segments(endpoint, 'loadbalancers', str(lb_id), 'nodes')

    d = treq.post(path,
                  headers=headers(auth_token),
                  data=json.dumps({"nodes": [{"address": ip_address,
                                              "port": port,
                                              "condition": "ENABLED",
                                              "type": "PRIMARY"}]}))
    d.addCallback(check_success, [200, 202])
    return d.addCallback(treq.json_content)


def add_to_load_balancers(endpoint, auth_token, lb_configs, ip_address):
    """
    Add the specified IP to mulitple load balancer based on the configs in
    lb_configs.

    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param list lb_configs: List of lb_config dictionaries.
    :param str ip_address: IP address of the node to add to the load balancer.

    :return: Deferred that fires with a list of 2-tuples of loadBalancerId, and
        Add Node response.
    """
    return gatherResults([
        add_to_load_balancer(
            endpoint,
            auth_token,
            lb_config,
            ip_address).addCallback(
                lambda response: (lb_config['loadBalancerId'], response))

        for lb_config in lb_configs
    ], consumeErrors=True)


def endpoints(service_catalog, service_name, region):
    """
    Search a service catalog for matching endpoints.

    :param list service_catalog: List of services.
    :param str service_name: Name of service.  Example: 'cloudServersOpenStack'
    :param str region: Region of service.  Example: 'ORD'

    :return: Iterable of endpoints.
    """
    for service in service_catalog:
        if service_name != service['name']:
            continue

        for endpoint in service['endpoints']:
            if region != endpoint['region']:
                continue

            yield endpoint


def public_endpoint_url(service_catalog, service_name, region):
    """
    Return the first publicURL for a given service in a given region.

    :param list service_catalog: List of services.
    :param str service_name: Name of service.  Example: 'cloudServersOpenStack'
    :param str region: Region of service.  Example: 'ORD'

    :return: URL as a string.
    """
    return list(endpoints(service_catalog, service_name, region))[0]['publicURL']


def private_ip_addresses(server):
    """
    Get all private IPv4 addresses from the addresses section of a server.

    :param dict server: A server body.
    :return: List of IP addresses as strings.
    """
    return [addr['addr'] for addr in server['server']['addresses']['private']
            if addr['version'] == 4]


def prepare_launch_config(scaling_group_uuid, launch_config):
    """
    Prepare a launch_config for the specified scaling_group.

    This is responsible for returning a copy of the launch config that
    has metadata and unique server names added.

    :param IScalingGroup scaling_group: The scaling group this server is
        getting launched for.

    :param dict launch_config: The complete launch_config args we want to build
        servers from.

    :return dict: The prepared launch config.
    """
    launch_config = deepcopy(launch_config)
    server_config = launch_config['server']

    if 'metadata' not in server_config:
        server_config['metadata'] = {}

    server_config['metadata']['rax:auto_scaling_group_id'] = scaling_group_uuid

    name_parts = [generate_server_name()]

    server_name_suffix = server_config.get('name')
    if server_name_suffix:
        name_parts.append(server_name_suffix)

    server_config['name'] = '-'.join(name_parts)

    for lb_config in launch_config.get('loadBalancers', []):
        if 'metadata' not in lb_config:
            lb_config['metadata'] = {}
        lb_config['metadata']['rax:auto_scaling_group_id'] = scaling_group_uuid
        lb_config['metadata']['rax:auto_scaling_server_name'] = server_config['name']

    return launch_config


def launch_server(log, region, scaling_group, service_catalog, auth_token, launch_config):
    """
    Launch a new server given the launch config auth tokens and service catalog.
    Possibly adding the newly launched server to a load balancer.

    :param BoundLog log: A bound logger.
    :param str region: A rackspace region as found in the service catalog.
    :param IScalingGroup scaling_group: The scaling group to add the launched
        server to.
    :param list service_catalog: A list of services as returned by the auth apis.
    :param str auth_token: The user's auth token.
    :param dict launch_config: A launch_config args structure as defined for
        the launch_server_v1 type.

    :return: Deferred that fires with a 2-tuple of server details and the
        list of load balancer responses from add_to_load_balancers.
    """
    launch_config = prepare_launch_config(scaling_group.uuid, launch_config)

    lb_region = config_value('regionOverrides.cloudLoadBalancers') or region
    cloudLoadBalancers = config_value('cloudLoadBalancers')
    cloudServersOpenStack = config_value('cloudServersOpenStack')

    log.msg(format="Looking for load balancer endpoint",
            service_name=cloudLoadBalancers,
            region=lb_region)

    lb_endpoint = public_endpoint_url(service_catalog,
                                      cloudLoadBalancers,
                                      lb_region)

    log.msg(format="Looking for cloud servers endpoint",
            service_name=cloudServersOpenStack,
            region=region)

    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)

    lb_config = launch_config.get('loadBalancers', [])

    server_config = launch_config['server']

    log = log.bind(server_name=server_config['name'])

    d = create_server(server_endpoint, auth_token, server_config)

    def _wait_for_server(server):
        ilog = log.bind(instance_id=server['server']['id'])
        return wait_for_status(
            ilog,
            server_endpoint,
            auth_token,
            server['server']['id'], 'ACTIVE')

    d.addCallback(_wait_for_server)

    def _add_lb(server):
        ip_address = private_ip_addresses(server)[0]
        lbd = add_to_load_balancers(lb_endpoint, auth_token, lb_config, ip_address)
        lbd.addCallback(lambda lb_response: (server, lb_response))
        return lbd

    d.addCallback(_add_lb)
    return d


def remove_from_load_balancer(endpoint, auth_token, loadbalancer_id, node_id):
    """
    Remove a node from a load balancer.

    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param str loadbalancer_id: The ID for a cloud loadbalancer.
    :param str node_id: The ID for a node in that cloudloadbalancer.

    :returns: A Deferred that fires with None if the operation completed successfully,
        or errbacks with an APIError.
    """
    path = append_segments(endpoint, 'loadbalancers', str(loadbalancer_id), 'nodes', str(node_id))
    d = treq.delete(path, headers=headers(auth_token))
    d.addCallback(check_success, [200, 202])
    d.addCallback(lambda _: None)
    return d


def delete_server(log, region, service_catalog, auth_token, instance_details):
    """
    Delete the server specified by instance_details.

    TODO: Load balancer draining.

    :param str region: A rackspace region as found in the service catalog.
    :param list service_catalog: A list of services as returned by the auth apis.
    :param str auth_token: The user's auth token.
    :param tuple instance_details: A 2-tuple of server details and a list of
        load balancer Add Node responses.

        Example::

        ({'server':
            {'id': 1,
             'ip_addresses': ...,
             'imageRef': ...}},
         [('12345',
           {'nodes': [{'id': 'a', 'address': ... }]}),
          ('54321',
           {'nodes': [{'id': 'b', 'address': ... }]})])

    :return: TODO
    """

    lb_region = config_value('regionOverrides.cloudLoadBalancers') or region
    cloudLoadBalancers = config_value('cloudLoadBalancers')
    cloudServersOpenStack = config_value('cloudServersOpenStack')

    log.msg(format="Looking for load balancer endpoint: %(service_name)s",
            service_name=cloudLoadBalancers,
            region=lb_region)

    lb_endpoint = public_endpoint_url(service_catalog,
                                      cloudLoadBalancers,
                                      lb_region)

    log.msg(format="Looking for cloud servers endpoint: %(service_name)s",
            service_name=cloudServersOpenStack,
            region=region)

    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)

    (server_details, loadbalancer_details) = instance_details

    node_info = itertools.chain(
        *[[(loadbalancer_id, node['id']) for node in node_details['nodes']]
          for (loadbalancer_id, node_details) in loadbalancer_details])

    d = gatherResults(
        [remove_from_load_balancer(lb_endpoint, auth_token, loadbalancer_id, node_id)
         for (loadbalancer_id, node_id) in node_info], consumeErrors=True)

    def when_removed_from_loadbalancers(_ignore):
        return treq.delete(
            append_segments(server_endpoint, 'servers', server_details['server']['id']),
            headers=headers(auth_token)).addCallback(check_success, [204])

    d.addCallback(when_removed_from_loadbalancers)
    return d
