"""
Initial implementation of a version one launch_server_v1 config.

This launch config worker is responsible for:
0) Generating server name and injecting our AS metadata
1) Starting a server
2) Adding the server to a load balancer.

On delete, this worker:
1) Removes the the server from the load balancer(s)
2) Deletes the server

Also no attempt is currently being made to define the public API for
initiating a launch_server job.
"""

import json
import re
from functools import partial
from urllib import urlencode

from pyrsistent import freeze, thaw

from toolz import comp

from twisted.internet.defer import (
    DeferredLock, DeferredSemaphore, gatherResults, inlineCallbacks,
    returnValue)
from twisted.internet.task import deferLater
from twisted.python.failure import Failure

from otter.auth import public_endpoint_url
from otter.convergence.composition import (
    json_to_LBConfigs,
    prepare_server_launch_config)
from otter.convergence.model import _servicenet_address
from otter.convergence.steps import UnexpectedServerStatus, set_server_name
from otter.util import logging_treq as treq
from otter.util.config import config_value
from otter.util.deferredutils import delay, log_with_time, retry_and_timeout
from otter.util.hashkey import generate_server_name
from otter.util.http import (
    APIError, RequestError, append_segments, check_success, headers,
    raise_error_on_code, wrap_request_error)
from otter.util.retry import (
    TransientRetryError, compose_retries, exponential_backoff_interval,
    random_interval, repeating_interval, retry, retry_times,
    terminal_errors_except, transient_errors_except)
from otter.worker._rcv3 import add_to_rcv3, remove_from_rcv3

# Number of times to retry when adding/removing nodes from LB
LB_MAX_RETRIES = 10

# Range from which random retry interval is got
LB_RETRY_INTERVAL_RANGE = [10, 15]


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
                    timeout=7200,
                    clock=None):
    """
    Wait until the server specified by server_id's status is 'ACTIVE'

    :param log: A bound logger.
    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth token.
    :param str server_id: Opaque nova server id.
    :param int interval: Polling interval in seconds.  Default: 20.
    :param int timeout: timeout to poll for the server status in seconds.
        Default 7200 (2 hours).

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


# single global instance of create server semaphore
_create_server_sem = None


def get_create_server_sempahore():
    """
    Get global instance of create server semaphore if configured. Otherwise
    return None
    """
    global _create_server_sem
    if _create_server_sem is not None:
        return _create_server_sem
    conf = config_value("worker.create_server_limit")
    if conf is None:
        return None
    _create_server_sem = DeferredSemaphore(conf)
    return _create_server_sem


class ServerCreationRetryError(Exception):
    """
    Exception to be raised when Nova behaves counter-intuitively, for instance
    if there is more than one server of a certain name
    """


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
    :raises: :class:`ServerCreationRetryError`
    """
    query_params = {
        'image': server_config.get('imageRef', ''),
        'flavor': server_config['flavorRef'],
        'name': '^{0}$'.format(re.escape(server_config['name']))
    }

    if query_params['image'] is None:
        query_params['image'] = ''

    url = '{path}?{query}'.format(
        path=append_segments(server_endpoint, 'servers', 'detail'),
        query=urlencode(query_params))

    def _check_if_server_exists(list_server_details):
        nova_servers = list_server_details['servers']

        if len(nova_servers) > 1:
            raise ServerCreationRetryError(
                "Nova returned {0} servers that match the same "
                "image/flavor and name {1}.".format(
                    len(nova_servers), server_config['name']))

        elif len(nova_servers) == 1:
            nova_server = list_server_details['servers'][0]

            if nova_server['metadata'] != server_config['metadata']:
                raise ServerCreationRetryError(
                    "Nova found a server of the right name ({name}) but wrong "
                    "metadata. Expected {expected_metadata} and got {nova_metadata}"
                    .format(expected_metadata=server_config['metadata'],
                            nova_metadata=nova_server['metadata'],
                            name=server_config['name']))

            return {'server': nova_server}

        return None

    d = treq.get(url, headers=headers(auth_token), log=log)
    d.addCallback(check_success, [200])
    d.addCallback(treq.json_content)
    d.addCallback(_check_if_server_exists)
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
                  clock=None, retries=3, create_failure_delay=5, _treq=None):
    """
    Create a new server.  If there is an error from Nova from this call,
    checks to see if the server was created anyway.  If not, will retry the
    create ``retries`` times (checking each time if a server).

    If the error from Nova is a 400, does not retry, because that implies that
    retrying will just result in another 400 (bad args).

    If checking to see if the server is created also results in a failure,
    does not retry because there might just be something wrong with Nova.

    :param str server_endpoint: Server endpoint URI.
    :param str auth_token: Keystone Auth Token.
    :param dict server_config: Nova server config.
    :param: int retries: Number of tries to retry the create.
    :param: int create_failure_delay: how much time in seconds to wait after
        a create server failure before checking Nova to see if a server
        was created

    :param log: logger
    :type log: :class:`otter.log.bound.BoundLog`

    :param _treq: To be used for testing - what treq object to use
    :type treq: something with the same api as :obj:`treq`

    :return: Deferred that fires with the CreateServer response as a dict.
    """
    path = append_segments(server_endpoint, 'servers')

    if _treq is None:  # pragma: no cover
        _treq = treq
    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    def _check_results(result, propagated_f):
        """
        Return the original failure, if checking a server resulted in a
        failure too.  Returns a wrapped propagated failure, if there were no
        servers created, so that the retry utility knows that server creation
        can be retried.
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
        """
        If creating a server failed with anything other than a 400, see if
        Nova created a server anyway (a 400 means that the server creation args
        were bad, and there is no point in retrying).

        If Nova created a server, just return it and pretend that the error
        never happened.  If it didn't, or if checking resulted in another
        failure response, return a failure of some type.
        """
        f.trap(APIError)
        if f.value.code == 400:
            return f

        d = deferLater(clock, create_failure_delay, find_server,
                       server_endpoint, auth_token, server_config, log=log)
        d.addBoth(_check_results, f)
        return d

    def _create_with_delay(to_delay):
        d = _treq.post(path, headers=headers(auth_token),
                       data=json.dumps({'server': server_config}), log=log)
        if to_delay:
            # Add 1 second delay to space 1 second between server creations
            d.addCallback(delay, clock, 1)
        return d

    def _create_server():
        """
        Attempt to create a server, handling spurious non-400 errors from Nova
        by seeing if Nova created a server anyway in spite of the error.  If so
        then create server succeeded.

        If not, and if no further errors occur, server creation can be retried.
        """
        create_server_sem = get_create_server_sempahore()
        if create_server_sem is not None:
            d = create_server_sem.run(_create_with_delay, True)
        else:
            d = _create_with_delay(False)
        d.addCallback(check_success, [202], _treq=_treq)
        d.addCallback(_treq.json_content)
        d.addErrback(_check_server_created)
        return d

    def _unwrap_NoCreatedServerFound(f):
        """
        The original failure was wrapped in a :class:`_NoCreatedServerFound`
        for ease of retry, but that should not be the final error propagated up
        by :func:`create_server`.

        This errback unwraps the :class:`_NoCreatedServerFound` error and
        returns the original failure.
        """
        f.trap(_NoCreatedServerFound)
        return f.value.original

    d = retry(
        _create_server,
        can_retry=compose_retries(
            retry_times(retries),
            terminal_errors_except(_NoCreatedServerFound)),
        next_interval=repeating_interval(15), clock=clock)

    d.addErrback(_unwrap_NoCreatedServerFound)
    d.addErrback(wrap_request_error, path, 'server_create')

    return d


def log_on_response_code(response, log, msg, code):
    """
    Log `msg` if response.code is same as code
    """
    if response.code == code:
        log.msg(msg)
    return response


def log_lb_unexpected_errors(f, log, msg):
    """
    Log load-balancer unexpected errors
    """
    if not f.check(APIError):
        log.err(f, 'Unknown error while ' + msg)
    elif not (f.value.code == 404 or
              f.value.code == 422 and 'PENDING_UPDATE' in f.value.body):
        log.msg('Got unexpected LB status {status_code} while {msg}: {error}',
                status_code=f.value.code, msg=msg, error=f.value)
    return f


class CLBOrNodeDeleted(Exception):
    """
    CLB or Node is deleted or in process of getting deleted

    :param :class:`RequestError` error: Error that caused this exception
    :param str clb_id: ID of deleted load balancer
    :param str node_id: ID of deleted node in above load balancer
    """
    def __init__(self, error, clb_id, node_id=None):
        super(CLBOrNodeDeleted, self).__init__(
            'CLB {} or node {} deleted due to {}'.format(clb_id, node_id, error))
        self.error = error
        self.clb_id = clb_id
        self.node_id = node_id


def check_deleted_clb(f, clb_id, node_id=None):
    """
    Raise :class:`CLBOrNodeDeleted` error based on information in `RequestError` in f.
    Otherwise return f

    :param :class:`Failure` f: failure containing :class:`RequestError`
                               from adding/removing node
    :param str clb_id: ID of load balancer causing the error
    :param str node_id: ID of node of above load balancer
    """
    # A LB being deleted sometimes results in a 422. This function
    # unfortunately has to parse the body of the message to see if this is an
    # acceptable 422 (if the LB has been deleted or in the process of being deleted)
    f.trap(RequestError)
    f.value.reason.trap(APIError)
    error = f.value.reason.value
    if error.code == 404:
        raise CLBOrNodeDeleted(f.value, clb_id, node_id)
    if error.code == 422:
        message = json.loads(error.body)['message']
        if ('load balancer is deleted' in message or 'PENDING_DELETE' in message):
            raise CLBOrNodeDeleted(f.value, clb_id, node_id)
    return f


def add_to_load_balancer(log, request_bag, lb_config, server_details, undo,
                         clock=None):
    """
    Adds a given server to a given load balancer.

    :param log: A bound logger.
    :param callable request_bag: A request function.
    :param str lb_config: An ``lb_config`` dictionary specifying which load
        balancer to add the server to.
    :param dict server_details: The server details, as returned by Nova.
    :return: Deferred that fires with the load balancer response. The
        structure of this object depends on the load balancer type.
    """
    lb_type = lb_config.get("type", "CloudLoadBalancer")
    if lb_type == "CloudLoadBalancer":
        cloudLoadBalancers = config_value('cloudLoadBalancers')
        endpoint = public_endpoint_url(request_bag.service_catalog,
                                       cloudLoadBalancers,
                                       request_bag.lb_region)
        auth_token = request_bag.auth_token
        ip_address = _servicenet_address(server_details["server"])
        return add_to_clb(log, endpoint, auth_token, lb_config, ip_address,
                          undo, clock)
    elif lb_type == "RackConnectV3":
        lb_id = lb_config["loadBalancerId"]
        server_id = server_details["server"]["id"]
        return add_to_rcv3(request_bag, lb_id, server_id)
    else:
        raise RuntimeError("Unknown cloud load balancer type! config: {}"
                           .format(lb_config))


def add_to_clb(log, endpoint, auth_token, lb_config, ip_address, undo, clock=None):
    """
    Add an IP address to a Cloud Load Balancer based on the ``lb_config``.

    TODO: Handle load balancer node metadata.

    :param log: A bound logger
    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone auth token.
    :param dict lb_config: An ``lb_config`` dictionary.
    :param str ip_address: The IP address of the node to add to the load
        balancer.
    :param IUndoStack undo: An IUndoStack to push any reversable operations
        onto.

    :return: Deferred that fires with the load balancer response.
    """
    lb_id = lb_config['loadBalancerId']
    port = lb_config['port']
    path = append_segments(endpoint, 'loadbalancers', str(lb_id), 'nodes')
    lb_log = log.bind(loadbalancer_id=lb_id, ip_address=ip_address)

    def add():
        d = treq.post(path, headers=headers(auth_token),
                      data=json.dumps({"nodes": [{"address": ip_address,
                                                  "port": port,
                                                  "condition": "ENABLED",
                                                  "type": "PRIMARY"}]}),
                      log=lb_log)
        d.addCallback(check_success, [200, 202])
        d.addErrback(log_lb_unexpected_errors, lb_log, 'add_node')
        d.addErrback(wrap_request_error, path, 'add_node')
        d.addErrback(check_deleted_clb, lb_id)
        return d

    d = retry(
        add,
        can_retry=compose_retries(
            transient_errors_except(CLBOrNodeDeleted),
            retry_times(config_value('worker.lb_max_retries') or LB_MAX_RETRIES)),
        next_interval=random_interval(
            *(config_value('worker.lb_retry_interval_range') or LB_RETRY_INTERVAL_RANGE)),
        clock=clock)

    def when_done(result):
        node_id = result['nodes'][0]['id']
        lb_log.msg('Added to load balancer', node_id=node_id)
        undo.push(_remove_from_clb, lb_log, endpoint, auth_token, lb_id,
                  node_id)
        return result

    return d.addCallback(treq.json_content).addCallback(when_done)


def add_to_load_balancers(log, request_bag, lb_configs, server, undo):
    """
    Add the given server to the load balancers specified by ``lb_configs``.

    :param log: A bound logger.
    :param callable request_bag: A request function.
    :param list lb_configs: List of lb_config dictionaries.
    :param dict server: Server dict of the server to add, as per server details
        response from Nova.
    :param IUndoStack undo: An IUndoStack to push any reversable operations onto.

    :return: Deferred that fires with a list of 2-tuples of the load
        balancer configuration, and that load balancer's respective response.
    """
    _add = partial(add_to_load_balancer, log, request_bag,
                   server_details=server, undo=undo)

    dl = DeferredLock()

    @inlineCallbacks
    def _serial_add(lb_config):
        yield dl.acquire()
        result = yield _add(lb_config)
        yield dl.release()
        returnValue(result)

    d = gatherResults(map(_serial_add, lb_configs), consumeErrors=True)
    return d.addCallback(partial(zip, lb_configs))


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
    launch_config = freeze(launch_config)

    lb_descriptions = json_to_LBConfigs(launch_config.get('loadBalancers', []))

    launch_config = prepare_server_launch_config(
        scaling_group_uuid, launch_config, lb_descriptions)

    suffix = generate_server_name()
    launch_config = set_server_name(launch_config, suffix)

    return thaw(launch_config)


def _without_otter_metadata(metadata):
    """
    Return a copy of the metadata with all the otter-specific keys
    removed.
    """
    meta = {k: v for (k, v) in metadata.get('metadata', {}).iteritems()
            if not (k.startswith("rax:auto_scaling") or
                    k.startswith("rax:autoscale:"))}
    return {'metadata': meta}


def scrub_otter_metadata(log, auth_token, service_catalog, region, server_id,
                         _treq=treq):
    """
    Scrub otter-specific management metadata from the server.

    :param BoundLog log: The bound logger instance.
    :param str auth_token: Keystone auth token.
    :param str region: The region the server is in.
    :param str server_id: The id of the server to remove metadata from.
    :param _treq: The treq instance; possibly a test double.
    """
    bound_log = log.bind(region=region, server_id=server_id)
    bound_log.msg("Scrubbing otter-specific metadata")

    service_name = config_value('cloudServersOpenStack')
    endpoint = public_endpoint_url(service_catalog, service_name, region)
    url = append_segments(endpoint, 'servers', server_id, 'metadata')

    auth_hdr = headers(auth_token)

    get, put = [lambda data=None, method=method: _treq.request(
        method, url, headers=auth_hdr, data=data, log=bound_log)
        for method in ["GET", "PUT"]]

    return (get()
            .addCallback(_treq.json_content)
            .addCallback(comp(json.dumps, _without_otter_metadata))
            .addCallback(put)
            .addCallback(_treq.content))


def launch_server(log, request_bag, scaling_group, launch_config, undo,
                  clock=None):
    """
    Launch a new server given the launch config auth tokens and service
    catalog. Possibly adding the newly launched server to a load balancer.

    :param BoundLog log: A bound logger.
    :param request_bag: An object with a bunch of useful data on it, including
        a callable to re-auth and get a new token.
    :param IScalingGroup scaling_group: The scaling group to add the launched
        server to.
    :param dict launch_config: A launch_config args structure as defined for
        the launch_server_v1 type.
    :param IUndoStack undo: The stack that will be rewound if undo fails.

    :return: Deferred that fires with a 2-tuple of server details and the
        list of load balancer responses from add_to_load_balancers.
    """
    launch_config = prepare_launch_config(scaling_group.uuid, launch_config)

    cloudServersOpenStack = config_value('cloudServersOpenStack')
    server_endpoint = public_endpoint_url(request_bag.service_catalog,
                                          cloudServersOpenStack,
                                          request_bag.region)

    lb_config = launch_config.get('loadBalancers', [])
    server_config = launch_config['server']

    log = log.bind(server_name=server_config['name'])
    ilog = [None]

    def check_metadata(server):
        # sanity check to make sure the metadata didn't change - can probably
        # be removed after a while if we do not see any log messages from this
        # function
        expected = launch_config['server']['metadata']
        result = server['server'].get('metadata')
        if result != expected:
            ilog[0].msg('Server metadata has changed.',
                        sanity_check=True,
                        expected_metadata=expected,
                        nova_metadata=result)
        return server

    def wait_for_server(server, new_request_bag):
        server_id = server['server']['id']

        # NOTE: If server create is retried, each server delete will be pushed
        # to undo stack even after it will be deleted in check_error which is
        # fine since verified_delete succeeds on deleted server
        undo.push(
            verified_delete, log, server_endpoint, new_request_bag, server_id)

        ilog[0] = log.bind(server_id=server_id)
        return wait_for_active(
            ilog[0],
            server_endpoint,
            new_request_bag.auth_token,
            server_id).addCallback(check_metadata)

    def add_lb(server, new_request_bag):
        if lb_config:
            lbd = add_to_load_balancers(
                ilog[0], new_request_bag, lb_config, server, undo)
            lbd.addCallback(lambda lb_response: (server, lb_response))
            return lbd

        return (server, [])

    def _real_create_server(new_request_bag):
        auth_token = new_request_bag.auth_token
        d = create_server(server_endpoint, auth_token, server_config, log=log)
        d.addCallback(wait_for_server, new_request_bag)
        d.addCallback(add_lb, new_request_bag)
        return d

    def _create_server():
        return request_bag.re_auth().addCallback(_real_create_server)

    def check_error(f):
        f.trap(UnexpectedServerStatus)
        if f.value.status == 'ERROR':
            log.msg('{server_id} errored, deleting and creating new '
                    'server instead', server_id=f.value.server_id)
            # trigger server delete and return True to allow retry
            verified_delete(log, server_endpoint, request_bag,
                            f.value.server_id)
            return True
        else:
            return False

    d = retry(_create_server,
              can_retry=compose_retries(retry_times(3), check_error),
              next_interval=repeating_interval(15), clock=clock)

    return d


def remove_from_load_balancer(log, request_bag, lb_config, lb_response,
                              clock=None):
    """
    Remove a node from a load balancer.

    :param BoundLog log: A bound logger.
    :param request_bag: A request function.
    :param dict lb_config: An ``lb_config`` dictionary.
    :param lb_response: The response the load balancer provided when the server
        being removed was added. Type and shape is dependant on type of load
        balancer.
    :param IReactorTime clock: An optional clock, for testing. Will be passed
        on to implementations of node removal logic for specific load balancer
        APIs, if they support a clock.
    :returns: A Deferred that fires with :data:`None` if the operation
        completed successfully, or errbacks with an RequestError.
    """
    lb_type = lb_config.get("type", "CloudLoadBalancer")
    if lb_type == "CloudLoadBalancer":
        cloudLoadBalancers = config_value('cloudLoadBalancers')
        endpoint = public_endpoint_url(request_bag.service_catalog,
                                       cloudLoadBalancers,
                                       request_bag.lb_region)
        auth_token = request_bag.auth_token
        loadbalancer_id = lb_config["loadBalancerId"]
        node_id = next(node_info["id"] for node_info in lb_response["nodes"])
        return _remove_from_clb(log, endpoint, auth_token, loadbalancer_id,
                                node_id, clock)
    elif lb_type == "RackConnectV3":
        lb_id = lb_config["loadBalancerId"]
        node_id = next(pair["cloud_server"]["id"] for pair in lb_response)
        return remove_from_rcv3(request_bag, lb_id, node_id)
    else:
        raise RuntimeError("Unknown cloud load balancer type! config: {}"
                           .format(lb_config))


def _remove_from_clb(log, endpoint, auth_token, loadbalancer_id, node_id, clock=None):
    """
    Remove a node from a CLB load balancer.

    :param str endpoint: Load balancer endpoint URI.
    :param str auth_token: Keystone authentication token.
    :param str loadbalancer_id: The ID for a Cloud Load Balancer.
    :param str node_id: The ID for a node in that Cloud Load Balancer.

    :returns: A Deferred that fires with None if the operation completed successfully,
        or errbacks with an RequestError.
    """
    lb_log = log.bind(loadbalancer_id=loadbalancer_id, node_id=node_id)
    # TODO: Will remove this once LB ERROR state is fixed and it is working fine
    lb_log.msg('Removing from load balancer')
    path = append_segments(endpoint, 'loadbalancers', str(loadbalancer_id), 'nodes', str(node_id))

    def remove():
        d = treq.delete(path, headers=headers(auth_token), log=lb_log)
        d.addCallback(check_success, [200, 202])
        d.addCallback(treq.content)  # To avoid https://twistedmatrix.com/trac/ticket/6751
        d.addErrback(log_lb_unexpected_errors, lb_log, 'remove_node')
        d.addErrback(wrap_request_error, path, 'remove_node')
        d.addErrback(check_deleted_clb, loadbalancer_id, node_id)
        return d

    d = retry(
        remove,
        can_retry=compose_retries(
            transient_errors_except(CLBOrNodeDeleted),
            retry_times(config_value('worker.lb_max_retries') or LB_MAX_RETRIES)),
        next_interval=random_interval(
            *(config_value('worker.lb_retry_interval_range') or LB_RETRY_INTERVAL_RANGE)),
        clock=clock)

    # A node or CLB deleted is considered successful removal
    d.addErrback(lambda f: f.trap(CLBOrNodeDeleted) and lb_log.msg(f.value.message))
    d.addCallback(lambda _: lb_log.msg('Removed from load balancer'))
    return d


def delete_server(log, request_bag, instance_details, clock=None):
    """
    Delete the server specified by instance_details.

    TODO: Load balancer draining.

    :param BoundLog log: A bound logger.
    :param callable request_bag: A request function.
    :param tuple instance_details: A 2-tuple of the server_id and a list of
        2-tuples of load balancer configurations and respective load balancer
        responses. Example for some CLB load balancers::

        ('da08965f-4c2d-41aa-b492-a3c02706202f',
         [({"loadBalancerId": '12345'},
           {'nodes': [{'id': 'a', 'address': ... }]}),
          ({"loadBalancerId": '54321'},
           {'nodes': [{'id': 'b', 'address': ... }]})])

        Historically, these lode balancer configurations were just CLB
        ids. This form is deprecated, but still supported::

        ('da08965f-4c2d-41aa-b492-a3c02706202f',
         [('12345',
           {'nodes': [{'id': 'a', 'address': ... }]}),
          ('54321',
           {'nodes': [{'id': 'b', 'address': ... }]})])

    :return: TODO

    """
    _remove_from_lb = partial(remove_from_load_balancer, log, request_bag)
    server_id, lb_details = _as_new_style_instance_details(instance_details)
    d = gatherResults([_remove_from_lb(lb_config, lb_response)
                       for (lb_config, lb_response) in lb_details],
                      consumeErrors=True)

    def when_removed_from_loadbalancers(_ignore):
        cloudServersOpenStack = config_value('cloudServersOpenStack')
        server_endpoint = public_endpoint_url(request_bag.service_catalog,
                                              cloudServersOpenStack,
                                              request_bag.region)
        return verified_delete(log, server_endpoint, request_bag, server_id,
                               clock=clock)

    d.addCallback(when_removed_from_loadbalancers)
    return d


def _definitely_lb_config(probably_lb_config):
    """
    Returns a load balancer configuration unscathed. If passed
    something that looks like a CLB id, synthesizes a fake load
    balancer configuration.

    :param probably_lb_config: An object that is probably a load balancer
        configuration, except maybe is just a CLB id.
    :type probably_lb_config: probably :class:`dict`, maybe :class:`str`

    :return: A load balancer configuration.
    :rtype: `class`:dict:
    """
    if isinstance(probably_lb_config, dict):
        return probably_lb_config
    else:
        return {"loadBalancerId": probably_lb_config}


def _as_new_style_instance_details(maybe_old_style):
    """
    Converts possibly old-style ``instance_details`` (with just a CLB
    id) to a new-style ``instance_details`` (with a load balancer
    configuration).

    If the passed ``instance_details`` are already new-style, they are passed
    unchanged.

    :param maybe_old_style: As ``instance_details``.
    :return: An ``instance_details``, definitely new-style.

    """
    server_id, lb_specs = maybe_old_style
    updated_lb_specs = [(_definitely_lb_config(maybe_lb_conf), lb_response)
                        for maybe_lb_conf, lb_response in lb_specs]
    return server_id, updated_lb_specs


# Allow only 1 delete server request at a time
MAX_DELETE_SERVER = 1
delete_server_sem = DeferredSemaphore(MAX_DELETE_SERVER)


def delete_and_verify(log, server_endpoint, request_bag, server_id, clock):
    """
    Check the status of the server to see if it's actually been deleted.
    Succeeds only if it has been either deleted (404) or acknowledged by Nova
    to be deleted (task_state = "deleted").

    Note that ``task_state`` is in the server details key
    ``OS-EXT-STS:task_state``, which is supported by Openstack but available
    only when looking at the extended status of a server.
    """
    path = append_segments(server_endpoint, 'servers', server_id)

    def delete_with_delay(_bag):
        d = treq.delete(path, headers=headers(_bag.auth_token), log=log)
        # Add 0.4 seconds delay to allow 150 requests per minute
        return d.addCallback(delay, clock, 0.4)

    def delete(_bag):
        del_d = delete_server_sem.run(delete_with_delay, _bag)
        del_d.addCallback(check_success, [404])
        del_d.addCallback(treq.content)
        return del_d.addErrback(verify, request_bag.auth_token)

    def check_task_state(json_blob):
        server_details = json_blob['server']
        is_deleting = server_details.get("OS-EXT-STS:task_state", "")
        if is_deleting.strip().lower() != "deleting":
            raise UnexpectedServerStatus(server_id, is_deleting, "deleting")

    def verify(f, auth_token):
        f.trap(APIError)
        if f.value.code != 204:
            return wrap_request_error(f, path, 'delete_server')

        ver_d = server_details(server_endpoint, auth_token, server_id, log=log)
        ver_d.addCallback(check_task_state)
        ver_d.addErrback(lambda f: f.trap(ServerDeleted))
        return ver_d

    return request_bag.re_auth().addCallback(delete)


def verified_delete(log,
                    server_endpoint,
                    request_bag,
                    server_id,
                    exp_start=2,
                    max_retries=10,
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
    :param int exp_start: Exponential backoff interval start seconds. Default 2
    :param int max_retries: Maximum number of retry attempts

    :return: Deferred that fires when the expected status has been seen.
    """
    serv_log = log.bind(server_id=server_id)
    serv_log.msg('Deleting server')

    if clock is None:  # pragma: no cover
        from twisted.internet import reactor
        clock = reactor

    d = retry(
        partial(delete_and_verify, serv_log, server_endpoint, request_bag,
                server_id, clock),
        can_retry=retry_times(max_retries),
        next_interval=exponential_backoff_interval(exp_start),
        clock=clock)

    d.addCallback(log_with_time, clock, serv_log, clock.seconds(),
                  ('Server deleted successfully (or acknowledged by Nova as '
                   'to-be-deleted) : {time_delete} seconds.'), 'time_delete')
    return d
