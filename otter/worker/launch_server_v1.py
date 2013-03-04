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
from copy import deepcopy

from twisted.internet.defer import Deferred, gatherResults
from twisted.internet.task import LoopingCall

import treq

from otter.util.http import append_segments
from otter.util.hashkey import generate_server_name


class APIError(Exception):
    """
    An error raised when a non-success response is returned by the API.

    :param int code: HTTP Response code for this error.
    :param str body: HTTP Response body for this error or None.
    """
    def __init__(self, code, body):
        Exception.__init__(
            self,
            'API Error code={0!r}, body={1!r}'.format(code, body))

        self.code = code
        self.body = body


def check_success(response, success_codes):
    """
    Convert an HTTP response to an appropriate APIError if
    the response code does not match an expected success code.

    This is intended to be used as a callback for a deferred that fires with
    an IResponse provider.

    :param IResponse response: The response to check.
    :param list success_codes: A list of int HTTP response codes that indicate
        "success".

    :return: response or a deferred that errbacks with an APIError.
    """
    def _raise_api_error(body):
        raise APIError(response.code, body)

    if response.code not in success_codes:
        return treq.content(response).addCallback(_raise_api_error)

    return response


def auth_headers(auth_token):
    """
    Generate an appropriate set of headers given an auth_token.

    :param str auth_token: The auth_token.
    :return: A dict of common headers.
    """
    return {'content-type': ['application/json'],
            'accept': ['application/json'],
            'x-auth-token': [auth_token]}


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
                 headers=auth_headers(auth_token))
    d.addCallback(check_success, [200, 203])
    return d.addCallback(treq.json_content)


def wait_for_status(server_endpoint,
                    auth_token,
                    server_id,
                    expected_status,
                    interval=5,
                    clock=None):
    """
    Wait until the server specified by server_id's status is expected_status.

    @TODO: Timeouts
    @TODO: Errback on error statuses.

    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth token.
    :param str server_id: Opaque nova server id.
    :param str expected_status: Nova status string.
    :param int interval: Polling interval.  Default: 5.

    :return: Deferred that fires when the expected status has been seen.
    """

    d = Deferred()

    def poll():
        def _check_status(server):
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

    # XXX: Is this where we should generate the name and insert metadata?
    #   Or should that already be in the server_config by the time we
    #   get here?  Perhaps an explicit prepare step that launch_server invokes?
    #   If that is the case scaling_group doesn't need to be passed in here.2
    d = treq.post(append_segments(server_endpoint, 'servers'),
                  headers=auth_headers(auth_token),
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
                  headers=auth_headers(auth_token),
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

    :return: Deferred that fires with the Add Node load balancer response
        for each lb_config in lb_configs or errbacks on the first error.
    """
    return gatherResults([
        add_to_load_balancer(endpoint, auth_token, lb_config, ip_address)
        for lb_config in lb_configs
    ], consumeErrors=True)


def endpoints(service_catalog, service_name=None, service_type=None, region=None):
    """
    Search a service catalog for matching endpoints.

    :param list service_catalog: List of services.
    :param str service_name: Name of service.  Example: 'cloudServersOpenStack'
    :param str service_type: Type of service. Example: 'compute'
    :param str region: Region of service.  Example: 'ORD'

    :return: Iterable of endpoints.
    """
    for service in service_catalog:
        if service_type and service_type != service['type']:
            continue

        if service_name and service_name != service['name']:
            continue

        for endpoint in service['endpoints']:
            if region and endpoint['region'] != region:
                continue

            yield endpoint


def private_ip_addresses(server):
    """
    Get all private IPv4 addresses from the addresses section of a server.

    :param dict server: A server body.
    :return: List of IP addresses as strings.
    """
    return [addr['addr'] for addr in server['server']['addresses']['private']
            if addr['version'] == 4]


def prepare_launch_config(scaling_group, launch_config):
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

    server_config['metadata']['rax:auto_scaling_group_id'] = scaling_group.uuid

    name_parts = [generate_server_name()]

    server_name_suffix = server_config.get('name')
    if server_name_suffix:
        name_parts.append(server_name_suffix)

    server_config['name'] = '-'.join(name_parts)

    for lb_config in launch_config.get('loadBalancers', []):
        if 'metadata' not in lb_config:
            lb_config['metadata'] = {}
        lb_config['metadata']['rax:auto_scaling_group_id'] = scaling_group.uuid
        lb_config['metadata']['rax:auto_scaling_server_name'] = server_config['name']

    return launch_config


def launch_server(region, service_catalog, auth_token, launch_config):
    """
    Launch a new server given the launch config auth tokens and service catalog.
    Possibly adding the newly launched server to a load balancer.

    :param IScalingGroup scaling_group: The scaling group to add the launched
        server to.
    :param str region: A rackspace region as found in the service catalog.
    :param list service_catalog: A list of services as returned by the auth apis.
    :param str auth_token: The user's auth token.
    :param dict launch_config: A launch_config args structure as defined for
        the launch_server_v1 type.

    :return: Deferred that fires when the server is "launched" based on the
        given configuration.

    TODO: Figure out if the return value is significant other than for
        communicating failure.
    """
    #launch_config = prepare_launch_config(scaling_group, launch_config)

    lb_endpoint = list(endpoints(
        service_catalog,
        service_name='cloudLoadBalancers',
        region=region))[0]['publicURL']

    server_endpoint = list(endpoints(
        service_catalog,
        service_name='cloudServersOpenStack',
        region=region))[0]['publicURL']

    lb_config = launch_config.get('loadBalancers', [])

    server_config = launch_config['server']

    d = create_server(server_endpoint, auth_token, server_config)

    def _wait_for_server(server):
        return wait_for_status(
            server_endpoint,
            auth_token,
            server['server']['id'], 'ACTIVE')

    d.addCallback(_wait_for_server)

    def _add_lb(server):
        ip_address = private_ip_addresses(server)[0]
        lbd = add_to_load_balancers(lb_endpoint, auth_token, lb_config, ip_address)
        lbd.addCallback(lambda _: server)
        return lbd

    d.addCallback(_add_lb)
    return d
