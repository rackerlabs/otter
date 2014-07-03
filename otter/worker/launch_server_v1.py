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

from functools import partial
import json
import itertools
from copy import deepcopy
import re
from urllib import urlencode

from twisted.python.failure import Failure
from twisted.internet.defer import gatherResults, maybeDeferred, DeferredSemaphore

from otter.util import logging_treq as treq

from otter.util.config import config_value
from otter.util.http import (append_segments, headers, check_success,
                             wrap_request_error, raise_error_on_code,
                             APIError, RequestError)
from otter.util.hashkey import generate_server_name
from otter.util.deferredutils import retry_and_timeout, log_with_time
from otter.util.retry import (retry, retry_times, repeating_interval,
                              transient_errors_except, TransientRetryError,
                              random_interval, compose_retries,
                              terminal_errors_except)

# Number of times to retry when adding/removing nodes from LB
LB_MAX_RETRIES = 10

# Range from which random retry interval is got
LB_RETRY_INTERVAL_RANGE = [10, 15]


class UnexpectedServerStatus(Exception):
    """
    An exception to be raised when a server is found in an unexpected state.
    """
    def __init__(self, server_id, status, expected_status):
        super(UnexpectedServerStatus, self).__init__(
            'Expected {server_id} to have {expected_status}, '
            'has {status}'.format(server_id=server_id,
                                  status=status,
                                  expected_status=expected_status)
        )
        self.server_id = server_id
        self.status = status
        self.expected_status = expected_status


class ServerDeleted(Exception):
    """
    An exception to be raised when a server was deleted unexpectedly.
    """
    def __init__(self, server_id):
        super(ServerDeleted, self).__init__(
            'Server {server_id} has been deleted unexpectedly.'.format(
                server_id=server_id))
        self.server_id = server_id


def server_details(server_endpoint, auth_token, server_id, log=None):
    """
    Fetch the details of a server as specified by id.

    :param str server_endpoint: A str base URI probably from the service
        catalog.

    :param str auth_token: The auth token.
    :param str server_id: The opaque ID of a server.

    :return: A dict of the server details.
    """
    path = append_segments(server_endpoint, 'servers', server_id)
    d = treq.get(path, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200, 203])
    d.addErrback(raise_error_on_code, 404, ServerDeleted(server_id),
                 path, 'server_details')
    return d.addCallback(treq.json_content)


def wait_for_active(log,
                    server_endpoint,
                    auth_token,
                    server_id,
                    interval=20,
                    timeout=3600,
                    clock=None):
    """
    Wait until the server specified by server_id's status is 'ACTIVE'

    :param log: A bound logger.
    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth token.
    :param str server_id: Opaque nova server id.
    :param int interval: Polling interval in seconds.  Default: 5.
    :param int timeout: timeout to poll for the server status in seconds.
        Default 3600 (1 hour)

    :return: Deferred that fires when the expected status has been seen.
    """
    log.msg("Checking instance status every {interval} seconds",
            interval=interval)

    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    start_time = clock.seconds()

    def poll():
        def check_status(server):
            status = server['server']['status']
            time_building = clock.seconds() - start_time

            if status == 'ACTIVE':
                log.msg(("Server changed from 'BUILD' to 'ACTIVE' within "
                         "{time_building} seconds"),
                        time_building=time_building)
                return server

            elif status != 'BUILD':
                log.msg("Server changed to '{status}' in {time_building} seconds",
                        time_building=time_building, status=status)
                raise UnexpectedServerStatus(
                    server_id,
                    status,
                    'ACTIVE')

            else:
                raise TransientRetryError()  # just poll again

        sd = server_details(server_endpoint, auth_token, server_id, log=log)
        sd.addCallback(check_status)
        return sd

    timeout_description = ("Waiting for server <{0}> to change from BUILD "
                           "state to ACTIVE state").format(server_id)

    return retry_and_timeout(
        poll, timeout,
        can_retry=transient_errors_except(UnexpectedServerStatus, ServerDeleted),
        next_interval=repeating_interval(interval),
        clock=clock,
        deferred_description=timeout_description)


# limit on 2 servers to be created simultaneously
MAX_CREATE_SERVER = 2
create_server_sem = DeferredSemaphore(MAX_CREATE_SERVER)


def find_server(server_endpoint, auth_token, server_config, log=None):
    """
    Given a server config, attempts to find a server created with that config.

    Uses the Nova list server details endpoint to filter out any server that
    does not have the exact server name (the filter is a regex, so can filter
    by ``^<name>$``), image ID, and flavor ID (both of which are exact filters).

    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param dict server_config: Nova server config.
    :param log: A bound logger

    :return: Deferred that fires with a server (in the format of a server
        detail response) that matches that server config and creation time, or
        None if none matches
    """
    query_params = {
        'image': server_config['server']['imageRef'],
        'flavor': server_config['server']['flavorRef'],
        'name': '^{0}$'.format(re.escape(server_config['server']['name']))
    }
    url = '{path}?{query}'.format(
        path=append_segments(server_endpoint, 'servers', 'detail'),
        query=urlencode(query_params))

    d = treq.get(url, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200])
    d.addCallback(treq.json_content)

    def get_server(list_server_details):
        server_metadata = server_config['server']['metadata']

        if len(list_server_details['servers']) > 1:
            log.err("More than 1 server of the same name was returned by Nova",
                    servers=list_server_details['servers'])

        matches = [s for s in list_server_details['servers']
                   if s['metadata'] == server_metadata]

        if len(matches) >= 1:
            return {'server': matches[0]}

        return None

    d.addCallback(get_server)
    return d


class _NoCreatedServerFound(Exception):
    """
    Exception to be used only to indicate that retrying a create server can be
    attempted.  The original create server failure is wrapped so that if there
    are no more retries, the original failure can be propagated.
    """
    def __init__(self, original_failure):
        self.original = original_failure


def create_server(server_endpoint, auth_token, server_config, log=None,
                  clock=None, retries=3):
    """
    Create a new server.  If there is an error from Nova from this call,
    checks to see if the server was created anyway.  If not, will retry the
    create ``retry_times`` (checking each time if a server)

    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param dict server_config: Nova server config.

    :return: Deferred that fires with the CreateServer response as a dict.
    """
    path = append_segments(server_endpoint, 'servers')

    def _check_results(result, propagated_f):
        """
        Return the original failure, if checking a server resulted in a
        failure too, or a wrapped propagated failure, if there were no servers
        created, so that the
        """
        if isinstance(result, Failure):
            log.msg("Attempt to find a created server in nova resulted in "
                    "{failure}. Propagating the original create error instead.",
                    failure=result)
            return propagated_f

        if result is None:
            raise _NoCreatedServerFound(propagated_f)

        return result

    def _check_server_created(f):
        f.trap(APIError)
        if f.value.code == 400:  # if it's a 400, nova would not create a server
            return f

        d = find_server(server_endpoint, auth_token, server_config, log=log)
        d.addBoth(_check_results, f)
        return d

    def _create_server():
        d = create_server_sem.run(treq.post, path, headers=headers(auth_token),
                                  data=json.dumps({'server': server_config}),
                                  log=log)
        d.addCallback(check_success, [202])
        d.addCallback(treq.json_content)
        d.addErrback(_check_server_created)
        return d

    d = retry(
        _create_server,
        can_retry=compose_retries(
            retry_times(retries),
            terminal_errors_except(_NoCreatedServerFound)),
        next_interval=repeating_interval(15), clock=clock)

    d.addErrback(lambda f: f.trap(_NoCreatedServerFound) and f.value.original)
    d.addErrback(wrap_request_error, path, 'server_create')

    return d


def log_on_response_code(response, log, msg, code):
    """
    Log `msg` if response.code is same as code
    """
    if response.code == code:
        log.msg(msg)
    return response


def log_lb_unexpected_errors(f, path, log, msg):
    """
    Log load-balancer unexpected errors
    """
    if not f.check(APIError):
        log.err(f, 'Unknown error while ' + msg)
        return f
    error = RequestError(f, path, msg)
    log.msg('Got LB error while {m}: {e}', m=msg, e=error)
    # TODO: Will do it after LB delete works fine
    # 422 is PENDING_UPDATE
    #if f.value.code != 422:
    #    log.msg('Unexpected status {status} while {msg}: {error}',
    #            msg=msg, status=f.value.code, error=error)
    raise error


def add_to_load_balancer(log, endpoint, auth_token, lb_config, ip_address, undo, clock=None):
    """
    Add an IP addressed to a load balancer based on the lb_config.

    TODO: Handle load balancer node metadata.

    :param log: A bound logger
    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param str lb_config: An lb_config dictionary.
    :param str ip_address: The IP Address of the node to add to the load
        balancer.
    :param IUndoStack undo: An IUndoStack to push any reversable operations onto.

    :return: Deferred that fires with the Add Node to load balancer response
        as a dict.
    """
    lb_id = lb_config['loadBalancerId']
    port = lb_config['port']
    path = append_segments(endpoint, 'loadbalancers', str(lb_id), 'nodes')
    lb_log = log.bind(loadbalancer_id=lb_id)

    def add():
        d = treq.post(path, headers=headers(auth_token),
                      data=json.dumps({"nodes": [{"address": ip_address,
                                                  "port": port,
                                                  "condition": "ENABLED",
                                                  "type": "PRIMARY"}]}),
                      log=lb_log)
        d.addCallback(check_success, [200, 202])
        d.addErrback(log_lb_unexpected_errors, path, lb_log, 'add_node')
        return d

    d = retry(
        add,
        can_retry=retry_times(config_value('worker.lb_max_retries') or LB_MAX_RETRIES),
        next_interval=random_interval(
            *(config_value('worker.lb_retry_interval_range') or LB_RETRY_INTERVAL_RANGE)),
        clock=clock)

    def when_done(result):
        lb_log.msg('Added to load balancer')
        undo.push(remove_from_load_balancer,
                  lb_log,
                  endpoint,
                  auth_token,
                  lb_id,
                  result['nodes'][0]['id'])
        return result

    return d.addCallback(treq.json_content).addCallback(when_done)


def add_to_load_balancers(log, endpoint, auth_token, lb_configs, ip_address, undo):
    """
    Add the specified IP to mulitple load balancer based on the configs in
    lb_configs.

    :param log: A bound logger
    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param list lb_configs: List of lb_config dictionaries.
    :param str ip_address: IP address of the node to add to the load balancer.
    :param IUndoStack undo: An IUndoStack to push any reversable operations onto.

    :return: Deferred that fires with a list of 2-tuples of loadBalancerId, and
        Add Node response.
    """
    lb_iter = iter(lb_configs)

    results = []

    def add_next(_):
        try:
            lb_config = lb_iter.next()

            d = add_to_load_balancer(log, endpoint, auth_token, lb_config, ip_address, undo)
            d.addCallback(lambda response, lb_id: (lb_id, response), lb_config['loadBalancerId'])
            d.addCallback(results.append)
            d.addCallback(add_next)
            return d
        except StopIteration:
            return results

    return maybeDeferred(add_next, None)


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

    if server_config.get('name'):
        server_name = server_config.get('name')
        server_config['name'] = '{0}-{1}'.format(server_name, generate_server_name())
    else:
        server_config['name'] = generate_server_name()

    for lb_config in launch_config.get('loadBalancers', []):
        if 'metadata' not in lb_config:
            lb_config['metadata'] = {}
        lb_config['metadata']['rax:auto_scaling_group_id'] = scaling_group_uuid
        lb_config['metadata']['rax:auto_scaling_server_name'] = server_config['name']

    return launch_config


def launch_server(log, region, scaling_group, service_catalog, auth_token,
                  launch_config, undo, clock=None):
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
    :param IUndoStack undo: The stack that will be rewound if undo fails.

    :return: Deferred that fires with a 2-tuple of server details and the
        list of load balancer responses from add_to_load_balancers.
    """
    launch_config = prepare_launch_config(scaling_group.uuid, launch_config)

    lb_region = config_value('regionOverrides.cloudLoadBalancers') or region
    cloudLoadBalancers = config_value('cloudLoadBalancers')
    cloudServersOpenStack = config_value('cloudServersOpenStack')

    lb_endpoint = public_endpoint_url(service_catalog,
                                      cloudLoadBalancers,
                                      lb_region)

    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)

    lb_config = launch_config.get('loadBalancers', [])

    server_config = launch_config['server']

    log = log.bind(server_name=server_config['name'])
    ilog = [None]

    def wait_for_server(server):
        server_id = server['server']['id']

        # NOTE: If server create is retried, each server delete will be pushed
        # to undo stack even after it will be deleted in check_error which is fine
        # since verified_delete succeeds on deleted server
        undo.push(
            verified_delete, log, server_endpoint, auth_token, server_id)

        ilog[0] = log.bind(server_id=server_id)
        return wait_for_active(
            ilog[0],
            server_endpoint,
            auth_token,
            server_id)

    def add_lb(server):
        ip_address = private_ip_addresses(server)[0]
        lbd = add_to_load_balancers(
            ilog[0], lb_endpoint, auth_token, lb_config, ip_address, undo)
        lbd.addCallback(lambda lb_response: (server, lb_response))
        return lbd

    def _create_server():
        d = create_server(server_endpoint, auth_token, server_config, log=log)
        d.addCallback(wait_for_server)
        d.addCallback(add_lb)
        return d

    def check_error(f):
        f.trap(UnexpectedServerStatus)
        if f.value.status == 'ERROR':
            log.msg('{server_id} errored, deleting and creating new server instead',
                    server_id=f.value.server_id)
            # trigger server delete and return True to allow retry
            verified_delete(log, server_endpoint, auth_token, f.value.server_id)
            return True
        else:
            return False

    d = retry(_create_server, can_retry=compose_retries(retry_times(3), check_error),
              next_interval=repeating_interval(15), clock=clock)

    return d


def remove_from_load_balancer(log, endpoint, auth_token, loadbalancer_id,
                              node_id, clock=None):
    """
    Remove a node from a load balancer.

    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param str loadbalancer_id: The ID for a cloud loadbalancer.
    :param str node_id: The ID for a node in that cloudloadbalancer.

    :returns: A Deferred that fires with None if the operation completed successfully,
        or errbacks with an RequestError.
    """
    lb_log = log.bind(loadbalancer_id=loadbalancer_id, node_id=node_id)
    # TODO: Will remove this once LB ERROR state is fixed and it is working fine
    lb_log.msg('Removing from load balancer')
    path = append_segments(endpoint, 'loadbalancers', str(loadbalancer_id), 'nodes', str(node_id))

    def check_422_deleted(failure):
        # A LB being deleted sometimes results in a 422.  This function
        # unfortunately has to parse the body of the message to see if this is an
        # acceptable 422 (if the LB has been deleted or the node has already been
        # removed, then 'removing from load balancer' as a task should be
        # successful - if the LB is in ERROR, then nothing more can be done to
        # it except resetting it - may as well remove the server.)
        failure.trap(APIError)
        error = failure.value
        if error.code == 422:
            message = json.loads(error.body)['message']
            if ('load balancer is deleted' not in message and
                    'PENDING_DELETE' not in message):
                return failure
            lb_log.msg(message)
        else:
            return failure

    def remove():
        d = treq.delete(path, headers=headers(auth_token), log=lb_log)

        # Success is 200/202.  An LB not being found is 404.  A node not being
        # found is a 404.  But a deleted LB sometimes results in a 422.
        d.addCallback(log_on_response_code, lb_log, 'Node to delete does not exist', 404)
        d.addCallback(check_success, [200, 202, 404])
        d.addCallback(treq.content)  # To avoid https://twistedmatrix.com/trac/ticket/6751
        d.addErrback(check_422_deleted)
        d.addErrback(log_lb_unexpected_errors, path, lb_log, 'remove_node')
        return d

    d = retry(
        remove,
        can_retry=retry_times(config_value('worker.lb_max_retries') or LB_MAX_RETRIES),
        next_interval=random_interval(
            *(config_value('worker.lb_retry_interval_range') or LB_RETRY_INTERVAL_RANGE)),
        clock=clock)
    d.addCallback(lambda _: lb_log.msg('Removed from load balancer'))
    return d


def delete_server(log, region, service_catalog, auth_token, instance_details):
    """
    Delete the server specified by instance_details.

    TODO: Load balancer draining.

    :param str region: A rackspace region as found in the service catalog.
    :param list service_catalog: A list of services as returned by the auth apis.
    :param str auth_token: The user's auth token.
    :param tuple instance_details: A 2-tuple of server_id and a list of
        load balancer Add Node responses.

        Example::

        ('da08965f-4c2d-41aa-b492-a3c02706202f',
         [('12345',
           {'nodes': [{'id': 'a', 'address': ... }]}),
          ('54321',
           {'nodes': [{'id': 'b', 'address': ... }]})])

    :return: TODO
    """
    lb_region = config_value('regionOverrides.cloudLoadBalancers') or region
    cloudLoadBalancers = config_value('cloudLoadBalancers')
    cloudServersOpenStack = config_value('cloudServersOpenStack')

    lb_endpoint = public_endpoint_url(service_catalog,
                                      cloudLoadBalancers,
                                      lb_region)

    server_endpoint = public_endpoint_url(service_catalog,
                                          cloudServersOpenStack,
                                          region)

    (server_id, loadbalancer_details) = instance_details

    node_info = itertools.chain(
        *[[(loadbalancer_id, node['id']) for node in node_details['nodes']]
          for (loadbalancer_id, node_details) in loadbalancer_details])

    d = gatherResults(
        [remove_from_load_balancer(log, lb_endpoint, auth_token, loadbalancer_id, node_id)
         for (loadbalancer_id, node_id) in node_info], consumeErrors=True)

    def when_removed_from_loadbalancers(_ignore):
        return verified_delete(log, server_endpoint, auth_token, server_id)

    d.addCallback(when_removed_from_loadbalancers)
    return d


def delete_and_verify(log, server_endpoint, auth_token, server_id):
    """
    Check the status of the server to see if it's actually been deleted.
    Succeeds only if it has been either deleted (404) or acknowledged by Nova
    to be deleted (task_state = "deleted").

    Note that ``task_state`` is in the server details key
    ``OS-EXT-STS:task_state``, which is supported by Openstack but available
    only when looking at the extended status of a server.
    """
    path = append_segments(server_endpoint, 'servers', server_id)

    def delete():
        del_d = treq.delete(path, headers=headers(auth_token), log=log)
        del_d.addCallback(check_success, [404])
        del_d.addCallback(treq.content)
        return del_d

    def check_task_state(json_blob):
        server_details = json_blob['server']
        is_deleting = server_details.get("OS-EXT-STS:task_state", "")
        if is_deleting.strip().lower() != "deleting":
            raise UnexpectedServerStatus(server_id, is_deleting, "deleting")

    def verify(f):
        f.trap(APIError)
        if f.value.code != 204:
            return wrap_request_error(f, path, 'delete_server')

        ver_d = server_details(server_endpoint, auth_token, server_id, log=log)
        ver_d.addCallback(check_task_state)
        ver_d.addErrback(lambda f: f.trap(ServerDeleted))
        return ver_d

    return delete().addErrback(verify)


def verified_delete(log,
                    server_endpoint,
                    auth_token,
                    server_id,
                    interval=10,
                    timeout=3660,
                    clock=None):
    """
    Attempt to delete a server from the server endpoint, and ensure that it is
    deleted by trying again until deleting/getting the server results in a 404
    or until ``OS-EXT-STS:task_state`` in server details is 'deleting',
    indicating that Nova has acknowledged that the server is to be deleted
    as soon as possible.

    Time out attempting to verify deletes after a period of time and log an
    error.

    :param log: A bound logger.
    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth token.
    :param str server_id: Opaque nova server id.
    :param int interval: Deletion interval in seconds - how long until
        verifying a delete is retried. Default: 5.
    :param int timeout: Seconds after which the deletion will be logged as a
        failure, if Nova fails to return a 404.  Default is 3660, because if
        the server is building, the delete will not happen until immediately
        after it has finished building.

    :return: Deferred that fires when the expected status has been seen.
    """
    serv_log = log.bind(server_id=server_id)
    serv_log.msg('Deleting server')

    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    timeout_description = (
        "Waiting for Nova to actually delete server {0} (or acknowledge delete)"
        .format(server_id))

    d = retry_and_timeout(
        partial(delete_and_verify, serv_log, server_endpoint, auth_token, server_id),
        timeout,
        next_interval=repeating_interval(interval),
        clock=clock,
        deferred_description=timeout_description)

    d.addCallback(log_with_time, clock, serv_log, clock.seconds(),
                  ('Server deleted successfully (or acknowledged by Nova as '
                   'to-be-deleted) : {time_delete} seconds.'), 'time_delete')
    d.addErrback(serv_log.err)
    return d
