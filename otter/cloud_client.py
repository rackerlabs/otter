"""
Integration point for HTTP clients in otter.
"""
import json
import re
from functools import partial, wraps

import attr

from characteristic import Attribute, attributes

from effect import (
    ComposedDispatcher,
    Effect,
    TypeDispatcher,
    catch,
    perform,
    sync_performer)

import six

from toolz.dicttoolz import get_in
from toolz.itertoolz import concat

from twisted.internet.defer import DeferredLock
from twisted.internet.task import deferLater

from txeffect import deferred_performer, perform as twisted_perform

from otter.auth import Authenticate, InvalidateToken, public_endpoint_url
from otter.constants import ServiceType
from otter.util.config import config_value
from otter.util.http import APIError, append_segments, try_json_with_keys
from otter.util.http import headers as otter_headers
from otter.util.pure_http import (
    add_bind_root,
    add_effect_on_response,
    add_error_handling,
    add_headers,
    add_json_request_data,
    add_json_response,
    has_code,
    request,
)


def add_bind_service(catalog, service_name, region, log, request_func):
    """
    Decorate a request function so requests are relative to a particular
    Rackspace/OpenStack endpoint found in the tenant's catalog.
    """
    @wraps(request_func)
    def service_request(*args, **kwargs):
        """
        Perform an HTTP request similar to the request from
        :func:`get_request_func`, with the additional feature of being bound to
        a specific Rackspace/OpenStack service, so that the path can be
        relative to the service endpoint.
        """
        endpoint = public_endpoint_url(catalog, service_name, region)
        bound_request = add_bind_root(endpoint, request_func)
        return bound_request(*args, **kwargs)
    return service_request


def service_request(
        service_type, method, url, headers=None, data=None,
        params=None, log=None,
        reauth_codes=(401, 403),
        success_pred=has_code(200),
        json_response=True):
    """
    Make an HTTP request to a Rackspace service, with a bunch of awesome
    behavior!

    :param otter.constants.ServiceType service_type: The service against
        which the request should be made.
    :param bytes method: HTTP method
    :param url: partial URL (appended to service endpoint)
    :param dict headers: base headers; will have auth headers added.
    :param data: JSON-able object or None.
    :param params: dict of query param ids to lists of values, or a list of
        tuples of query key to query value.
    :param log: log to send request info to.
    :param sequence success_pred: A predicate of responses which determines if
        a response indicates success or failure.
    :param sequence reauth_codes: HTTP codes upon which to invalidate the
        auth cache.
    :param bool json_response: Specifies whether the response should be
        parsed as JSON.
    :param bool parse_errors: Whether to parse :class:`APIError`

    :raise APIError: Raised asynchronously when the response HTTP code is not
        in success_codes.
    :return: Effect of :obj:`ServiceRequest`, resulting in a JSON-parsed HTTP
        response body.
    """
    return Effect(ServiceRequest(
        service_type=service_type,
        method=method,
        url=url,
        headers=headers,
        data=data,
        params=params,
        log=log,
        reauth_codes=reauth_codes,
        success_pred=success_pred,
        json_response=json_response))


@attributes(["service_type", "method", "url", "headers", "data", "params",
             "log", "reauth_codes", "success_pred", "json_response"])
class ServiceRequest(object):
    """
    A request to a Rackspace/OpenStack service.

    Note that this intent does _not_ contain a tenant ID. To specify the tenant
    ID for any tree of effects that might contain a ServiceRequest, wrap the
    effect in a :obj:`TenantScope`.

    If you wrap :obj:`TenantScope` around effects of :obj:`ServiceRequest`,
    then you don't need to worry about including a performer for this
    :obj:`ServiceRequest` in your dispatcher -- :obj:`TenantScope`'s performer
    takes care of that.

    The result will be a two-tuple of a treq response object and the body
    of the response (either a json-compatible object or a string, depending
    on ``json_response``).
    """
    def intent_result_pred(self, result):
        """Check if the result looks like (treq response, body)."""
        # This type is not wide enough -- json objects can be strings and
        # numbers, too. It's also not *thin* enough, since this will allow
        # lists and dicts of *anything*. But it's a good approximation of what
        # rackspace/openstack services can return.
        return (isinstance(result, tuple) and
                isinstance(result[1],
                           (dict, list) if self.json_response else str))


@attributes(['effect', 'tenant_id'], apply_with_init=False)
class TenantScope(object):
    """
    An intent that specifies a tenant for any effect which might make
    :obj:`ServiceRequest`s.

    In other words, something like this::

        perform(dispatcher, TenantScope(Effect(ServiceRequest(...))))

    will make the ServiceRequest bound to the specified tenant.

    Use a partially-applied :func:`perform_tenant_scope` as the performer
    for this intent in your dispatcher.
    """
    def __init__(self, effect, tenant_id):
        self.effect = effect
        self.tenant_id = tenant_id


def concretize_service_request(
        authenticator, log, service_configs, throttler,
        tenant_id,
        service_request):
    """
    Translate a high-level :obj:`ServiceRequest` into a low-level :obj:`Effect`
    of :obj:`pure_http.Request`. This doesn't directly conform to the Intent
    performer interface, but it's intended to be used by a performer.

    :param ICachingAuthenticator authenticator: the caching authenticator
    :param BoundLog log: info about requests will be logged to this.
    :param dict service_configs: As returned by
        :func:`otter.constants.get_service_configs`.
    :param callable throttler: A function of ServiceType, HTTP method ->
        Deferred bracketer or None, used to throttle requests. See
        :obj:`_Throttle`.
    :param tenant_id: tenant ID.
    """
    auth_eff = Effect(Authenticate(authenticator, tenant_id, log))
    invalidate_eff = Effect(InvalidateToken(authenticator, tenant_id))
    if service_request.log is not None:
        log = service_request.log

    service_config = service_configs[service_request.service_type]
    region = service_config['region']
    service_name = service_config['name']

    def got_auth((token, catalog)):
        request_ = add_headers(otter_headers(token), request)
        request_ = add_effect_on_response(
            invalidate_eff, service_request.reauth_codes, request_)
        request_ = add_json_request_data(request_)
        if 'url' in service_config:
            request_ = add_bind_root(service_config['url'], request_)
        else:
            request_ = add_bind_service(
                catalog, service_name, region, log, request_)
        request_ = add_error_handling(
            service_request.success_pred, request_)
        if service_request.json_response:
            request_ = add_json_response(request_)

        return request_(
            service_request.method,
            service_request.url,
            headers=service_request.headers,
            data=service_request.data,
            params=service_request.params,
            log=log)

    eff = auth_eff.on(got_auth)
    bracket = throttler(service_request.service_type,
                        service_request.method.lower())
    if bracket is not None:
        return Effect(_Throttle(bracket=bracket, effect=eff))
    else:
        return eff


@attributes(['bracket', 'effect'])
class _Throttle(object):
    """
    A grody hack to allow using a Deferred concurrency limiter in Effectful
    code.

    A "Deferred bracket" is some function of type
    ``((f, *args, **kwargs) -> Deferred) -> Deferred``
    basically, something that "brackets" a call to some Deferred-returning
    function. This is the case for the ``run`` method of objects like
    :obj:`.DeferredSemaphore` and :obj:`.DeferredLock`.

    https://wiki.haskell.org/Bracket_pattern

    Ideally Effect would just have built-in concurrency limiters/idioms without
    relying on Twisted and Deferreds.

    :param callable bracket: The bracket to run the effect in
    :param Effect effect: The effect to perform inside the bracket
    """


@deferred_performer
def _perform_throttle(dispatcher, throttle):
    """
    Perform :obj:`_Throttle` by performing the effect after acquiring a lock
    and delaying but some period of time.
    """
    lock = throttle.bracket
    eff = throttle.effect
    return lock(twisted_perform, dispatcher, eff)


def _serialize_and_delay(clock, delay):
    """
    Return a function that when invoked with another function will run it
    serialized and after a delay.
    """
    lock = DeferredLock()
    return partial(lock.run, deferLater, clock, delay)


def _default_throttler(clock, stype, method):
    """Get a throttler function with default throttling policies."""
    # Serialize creation and deletion of cloud servers because the Compute team
    # has suggested we do this.

    # Compute suggested 150 deletion req/min. A delay of 0.4 should guarantee
    # no more than that are executed by a node, plus serialization of requests
    # will make it quite a bit lower than that.

    cloud_client_config = config_value('cloud_client')
    if cloud_client_config is None:
        cloud_client_config = {}
    throttling_config = cloud_client_config.get('throttling', {})
    create_server_delay = throttling_config.get('create_server_delay', 1)
    delete_server_delay = throttling_config.get('delete_server_delay', 0.4)

    policy = {
        (ServiceType.CLOUD_SERVERS, 'post'):
            _serialize_and_delay(clock, create_server_delay),
        (ServiceType.CLOUD_SERVERS, 'delete'):
            _serialize_and_delay(clock, delete_server_delay),
    }
    return policy.get((stype, method))


def perform_tenant_scope(
        authenticator, log, service_configs, throttler,
        dispatcher, tenant_scope, box,
        _concretize=concretize_service_request):
    """
    Perform a :obj:`TenantScope` by performing its :attr:`TenantScope.effect`,
    with a dispatcher extended with a performer for :obj:`ServiceRequest`
    intents. The performer will use the tenant provided by the
    :obj:`TenantScope`.

    The first arguments before (dispatcher, tenant_scope, box) are intended
    to be partially applied, and the result is a performer that can be put into
    a dispatcher.
    """
    @sync_performer
    def scoped_performer(dispatcher, service_request):
        return _concretize(
            authenticator, log, service_configs, throttler,
            tenant_scope.tenant_id, service_request)
    new_disp = ComposedDispatcher([
        TypeDispatcher({ServiceRequest: scoped_performer}),
        dispatcher])
    perform(new_disp, tenant_scope.effect.on(box.succeed, box.fail))


def get_cloud_client_dispatcher(reactor, authenticator, log, service_configs):
    """
    Get a dispatcher suitable for running :obj:`ServiceRequest` and
    :obj:`TenantScope` intents.
    """
    # this throttler could be parameterized but for now it's basically a hack
    # that we want to keep private to this module
    throttler = partial(_default_throttler, reactor)
    return TypeDispatcher({
        TenantScope: partial(perform_tenant_scope, authenticator, log,
                             service_configs, throttler),
        _Throttle: _perform_throttle,
    })


# ----- CLB requests and error parsing -----
def _regex(pattern):
    """
    Compile a case-insensitive pattern.
    """
    return re.compile(pattern, re.I)


_CLB_IMMUTABLE_PATTERN = _regex(
    "Load\s*Balancer '\d+' has a status of '[^']+' and is considered "
    "immutable")
_CLB_NOT_ACTIVE_PATTERN = _regex("Load\s*Balancer is not ACTIVE")
_CLB_DELETED_PATTERN = _regex(
    "(Load\s*Balancer '\d+' has a status of 'PENDING_DELETE' and is|"
    "The load balancer is deleted and) considered immutable")
_CLB_MARKED_DELETED_PATTERN = _regex(
    "The load\s*balancer is marked as deleted")
_CLB_NO_SUCH_NODE_PATTERN = _regex(
    "Node with id #\d+ not found for load\s*balancer #\d+$")
_CLB_NO_SUCH_LB_PATTERN = _regex(
    "Load\s*balancer not found")
_CLB_DUPLICATE_NODES_PATTERN = _regex(
    "Duplicate nodes detected. One or more nodes already configured "
    "on load\s*balancer")
_CLB_NODE_LIMIT_PATTERN = _regex(
    "Nodes must not exceed \d+ per load\s*balancer")
_CLB_NODE_REMOVED_PATTERN = _regex(
    "Node ids ((?:\d+,)*(?:\d+)) are not a part of your load\s*balancer")
_CLB_OVER_LIMIT_PATTERN = _regex("OverLimit Retry\.{3}")


@attr.s(these={"message": attr.ib()}, init=False)
class ExceptionWithMessage(Exception):
    """
    The builtin `Exception` doesn't have equality (it tests for identity).
    ``attr`` provides equality based on the attributes.

    But letting ``attr`` generate the `__init__` function for you means that
    means extra kwargs do not get passed to the superclass's
    ``__init__``.

    So this gives us a base class that does both.  By using providing
    our own ``__init__`` function, we can make this compatible with the builtin
    Exception and also get the Python27 Exception's ``__str__`` function
    automatically.

    Also useful to note that Python 3 does not store the message on the
    Exception, it just stores the args passed to it, so this lets us have a
    message attribute in Python 3 as well.
    """
    def __init__(self, message):
        """
        Set ``self.message`` and also call the base class's ``__init__``.
        """
        super(ExceptionWithMessage, self).__init__(message)
        self.message = message


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBImmutableError(Exception):
    """
    Error to be raised when the CLB is in some status that causes is to be
    temporarily immutable.

    This exception is _not_ used when the status is PENDING_DELETE. See
    :obj:`NoSuchCLBError`.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class NoSuchCLBError(Exception):
    """
    Error to be raised when the CLB does not exist or is being deleted.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type),
             Attribute('node_id', instance_of=six.text_type)])
class NoSuchCLBNodeError(Exception):
    """
    Error to be raised when attempting to modify a CLB node that no longer
    exists.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBNotActiveError(Exception):
    """
    Error to be raised when a CLB is not ACTIVE (and we have no more
    information about what its actual state is).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBRateLimitError(Exception):
    """
    Error to be raised when CLB returns 413 (rate limiting).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBDuplicateNodesError(Exception):
    """
    Error to be raised only when adding one or more nodes to a CLB whose
    address and port are mapped on the CLB.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBNodeLimitError(Exception):
    """
    Error to be raised only when adding one or more nodes to a CLB: adding
    that number of nodes would exceed the maximum number of nodes allowed on
    the CLB.
    """


def _match_errors(code_keys_exc_mapping, status_code, response_dict):
    """
    Take a list of tuples of:
    (status code, json keys, regex pattern (optional), exception callable),
    and attempt to match them against the given status code and response
    dict.  If a match is found raises the given exception type with the
    exception callable, passing along the message.
    """
    for code, keys, pattern, make_exc in code_keys_exc_mapping:
        if code == status_code:
            message = get_in(keys, response_dict, None)
            if message is not None and (not pattern or pattern.match(message)):
                raise make_exc(message)


def _only_json_api_errors(f):
    """
    Helper function so that we only catch APIErrors with bodies that can be
    parsed into JSON.

    Should decorate a function that expects two parameters: http status code
    and JSON body.

    If the decorated function cannot parse the error (either because it's not
    JSON or not recognized), reraise the error.
    """
    @wraps(f)
    def try_parsing(api_error_exc_info):
        api_error = api_error_exc_info[1]
        try:
            body = json.loads(api_error.body)
        except (ValueError, TypeError):
            pass
        else:
            f(api_error.code, body)

        six.reraise(*api_error_exc_info)

    return catch(APIError, try_parsing)


def add_clb_nodes(lb_id, nodes):
    """
    Generate effect to add one or more nodes to a load balancer.

    Note: This is not correctly documented in the load balancer documentation -
    it is documented as "Add Node" (singular), but the examples show multiple
    nodes being added.

    :param str lb_id: The load balancer ID to add the nodes to
    :param list nodes: A list of node dictionaries that each look like::

        {
            "address": "valid ip address",
            "port": 80,
            "condition": "ENABLED",
            "weight": 1,
            "type": "PRIMARY"
        }

        (weight and type are optional)

    :return: :class:`ServiceRequest` effect

    :raises: :class:`CLBImmutableError`,
        :class:`NoSuchCLBError`, :class:`CLBDuplicateNodesError`,
        :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'POST',
        append_segments('loadbalancers', lb_id, 'nodes'),
        data={'nodes': nodes},
        success_pred=has_code(202))

    @_only_json_api_errors
    def _parse_known_errors(code, json_body):
        mappings = _expand_clb_matches(
            [(422, _CLB_DUPLICATE_NODES_PATTERN, CLBDuplicateNodesError),
             (413, _CLB_NODE_LIMIT_PATTERN, CLBNodeLimitError)],
            lb_id)
        _match_errors(mappings, code, json_body)
        _process_clb_api_error(code, json_body, lb_id)

    return eff.on(error=_parse_known_errors)


def change_clb_node(lb_id, node_id, condition, weight):
    """
    Generate effect to change a node on a load balancer.

    :param str lb_id: The load balancer ID to add the nodes to
    :param str node_id: The node id to change.
    :param str condition: The condition to change to: one of "ENABLED",
        "DRAINING", or "DISABLED"
    :param int weight: The weight to change to.

    Note: this does not support "type" yet, since it doesn't make sense to add
    autoscaled servers as secondary.

    :return: :class:`ServiceRequest` effect

    :raises: :class:`CLBImmutableError`,
        :class:`NoSuchCLBError`, :class:`NoSuchCLBNodeError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'PUT',
        append_segments('loadbalancers', lb_id, 'nodes', node_id),
        data={'condition': condition, 'weight': weight},
        success_pred=has_code(202))

    @_only_json_api_errors
    def _parse_known_errors(code, json_body):
        _process_clb_api_error(code, json_body, lb_id)
        _match_errors(
            _expand_clb_matches(
                [(404, _CLB_NO_SUCH_NODE_PATTERN, NoSuchCLBNodeError)],
                lb_id=lb_id, node_id=node_id),
            code,
            json_body)

    return eff.on(error=_parse_known_errors)


def remove_clb_nodes(lb_id, node_ids):
    """
    Remove multiple nodes from a load balancer.

    :param str lb_id: A load balancer ID.
    :param node_ids: iterable of node IDs.
    :return: Effect of None.

    Succeeds on 202.

    This function will handle the case where *some* of the nodes are valid and
    some aren't, by retrying deleting only the valid ones.
    """
    node_ids = map(str, node_ids)
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'DELETE',
        append_segments('loadbalancers', lb_id, 'nodes'),
        params={'id': node_ids},
        success_pred=has_code(202))

    def check_invalid_nodes(exc_info):
        code = exc_info[1].code
        body = exc_info[1].body
        if code == 400:
            message = try_json_with_keys(
                body, ["validationErrors", "messages", 0])
            if message is not None:
                match = _CLB_NODE_REMOVED_PATTERN.match(message)
                if match:
                    removed = concat([group.split(',')
                                      for group in match.groups()])
                    return remove_clb_nodes(lb_id,
                                            set(node_ids) - set(removed))
        six.reraise(*exc_info)

    return eff.on(
        error=catch(APIError, check_invalid_nodes)
    ).on(
        error=_only_json_api_errors(
            lambda c, b: _process_clb_api_error(c, b, lb_id))
    ).on(success=lambda _: None)


def _expand_clb_matches(matches_tuples, lb_id, node_id=None):
    """
    All CLB messages have only the keys ("message",), and the exception tpye
    takes a load balancer ID and maybe a node ID.  So expand a tuple that looks
    like:

    (code, pattern, exc_type)

    to

    (code, ("message",), pattern, partial(exc_type, lb_id=lb_id))

    and maybe the partial will include the node ID too if it's provided.
    """
    params = {"lb_id": six.text_type(lb_id)}
    if node_id is not None:
        params["node_id"] = six.text_type(node_id)

    return [(m[0], ("message",), m[1], partial(m[2], **params))
            for m in matches_tuples]


def _process_clb_api_error(api_error_code, json_body, lb_id):
    """
    Attempt to parse generic CLB API error messages, and raise recognized
    exceptions in their place.

    :param int api_error_code: The status code from the HTTP request
    :param dict json_body: The error message, parsed as a JSON dict.
    :param string lb_id: The load balancer ID

    :raises: :class:`CLBImmutableError`,
        :class:`NoSuchCLBError`, :class:`APIError` by itself
    """
    mappings = (
        # overLimit is different than the other CLB messages because it's
        # produced by repose
        [(413, ("overLimit", "message"), _CLB_OVER_LIMIT_PATTERN,
          partial(CLBRateLimitError, lb_id=six.text_type(lb_id)))] +
        _expand_clb_matches(
            [(422, _CLB_DELETED_PATTERN, NoSuchCLBError),
             (410, _CLB_MARKED_DELETED_PATTERN, NoSuchCLBError),
             (422, _CLB_IMMUTABLE_PATTERN, CLBImmutableError),
             (422, _CLB_NOT_ACTIVE_PATTERN, CLBNotActiveError),
             (404, _CLB_NO_SUCH_LB_PATTERN, NoSuchCLBError)],
            lb_id))
    return _match_errors(mappings, api_error_code, json_body)


# ----- Nova requests and error parsing -----

def _forbidden_plaintext(message):
    return _regex(
        "403 Forbidden\s+Access was denied to this resource\.\s+({0})$"
        .format(message))

_NOVA_403_NO_PUBLIC_NETWORK = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000\) not allowed")
_NOVA_403_PUBLIC_SERVICENET_BOTH_REQUIRED = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000,"
    "11111111-1111-1111-1111-111111111111\) required but missing")
_NOVA_403_RACKCONNECT_NETWORK_REQUIRED = _forbidden_plaintext(
    "Exactly 1 isolated network\(s\) must be attached")
_NOVA_403_QUOTA = _regex(
    "Quota exceeded for (\S+): Requested \d+, but already used \d+ of \d+ "
    "(\S+)")


@attributes([Attribute('server_id', instance_of=six.text_type)])
class NoSuchServerError(Exception):
    """
    Exception to be raised when there is no such server in Nova.
    """


@attributes([Attribute('server_id', instance_of=six.text_type)])
class ServerMetadataOverLimitError(Exception):
    """
    Exception to be raised when there are too many metadata items on the
    server already.
    """


class NovaRateLimitError(ExceptionWithMessage):
    """
    Exception to be raised when Nova has rate-limited requests.
    """


class NovaComputeFaultError(ExceptionWithMessage):
    """
    Exception to be raised when there is a service failure from Nova.
    """


class CreateServerConfigurationError(ExceptionWithMessage):
    """
    Exception to be raised when creating a server with invalid arguments.  The
    message to be returned is the message that comes back from Nova.
    """


class CreateServerOverQuoteError(ExceptionWithMessage):
    """
    Exception to be raised when unable to create a server because the quote for
    some item (e.g. RAM, instances, on-metal instances) has been exceeded.

    This could possibly be parsed down into more structured data eventually,
    since the string format is the same no matter what the quota is for.
    """


_MAX_METADATA_PATTERN = _regex('Maximum number of metadata items')


def set_nova_metadata_item(server_id, key, value):
    """
    Set metadata key/value item on the given server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)

    Succeed on 200.

    :raise: :class:`NoSuchServer`, :class:`MetadataOverLimit`,
        :class:`NovaRateLimitError`, :class:`NovaComputeFaultError`,
        :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'PUT',
        append_segments('servers', server_id, 'metadata', key),
        data={'meta': {key: value}},
        reauth_codes=(401,),
        success_pred=has_code(200))

    @_only_json_api_errors
    def _parse_known_errors(code, json_body):
        other_errors = [
            (404, ('itemNotFound', 'message'), None,
             partial(NoSuchServerError, server_id=six.text_type(server_id))),
            (403, ('forbidden', 'message'), _MAX_METADATA_PATTERN,
             partial(ServerMetadataOverLimitError,
                     server_id=six.text_type(server_id))),
        ]
        _match_errors(_nova_standard_errors + other_errors, code, json_body)

    return eff.on(error=_parse_known_errors)


def get_server_details(server_id):
    """
    Get details for one particular server.

    :ivar str server_id: a Nova server ID.

    Succeed on 200.

    :raise: :class:`NoSuchServer`, :class:`NovaRateLimitError`,
        :class:`NovaComputeFaultError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'GET',
        append_segments('servers', server_id),
        success_pred=has_code(200))

    @_only_json_api_errors
    def _parse_known_errors(code, json_body):
        other_errors = [
            (404, ('itemNotFound', 'message'), None,
             partial(NoSuchServerError, server_id=six.text_type(server_id))),
        ]
        _match_errors(_nova_standard_errors + other_errors, code, json_body)

    return eff.on(error=_parse_known_errors)


def create_server(server_args):
    """
    Create a server using Nova.

    :ivar dict server_args:  The dictionary to pass to Nova specifying how
        the server should be built.

    Succeed on 202, and only reauthenticate on 401 because 403s may be terminal
    errors.

    :raise: :class:`CreateServerConfigurationError`,
        :class:`CreateServerOverQuoteError`, :class:`NovaRateLimitError`,
        :class:`NovaComputFaultError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'POST',
        'servers',
        data=server_args,
        success_pred=has_code(202),
        reauth_codes=(401,))

    @_only_json_api_errors
    def _parse_known_json_errors(code, json_body):
        other_errors = [
            (400, ('badRequest', 'message'), None,
             CreateServerConfigurationError),
            (403, ('forbidden', 'message'), _NOVA_403_QUOTA,
             CreateServerOverQuoteError)
        ]
        _match_errors(_nova_standard_errors + other_errors, code, json_body)

    def _parse_known_string_errors(api_error_exc_info):
        api_error = api_error_exc_info[1]
        if api_error.code == 403:
            for pat in (_NOVA_403_RACKCONNECT_NETWORK_REQUIRED,
                        _NOVA_403_NO_PUBLIC_NETWORK,
                        _NOVA_403_PUBLIC_SERVICENET_BOTH_REQUIRED):
                m = pat.match(api_error.body)
                if m:
                    raise CreateServerConfigurationError(m.groups()[0])

        six.reraise(*api_error_exc_info)

    return (eff
            .on(error=catch(APIError, _parse_known_string_errors))
            .on(error=_parse_known_json_errors))


_nova_standard_errors = [
    (413, ('overLimit', 'message'), None, NovaRateLimitError),
    (500, ('computeFault', 'message'), None, NovaComputeFaultError)
]


# ----- Cloud feeds requests -----
def publish_to_cloudfeeds(event, log=None):
    """
    Publish an event dictionary to cloudfeeds.
    """
    return service_request(
        ServiceType.CLOUD_FEEDS, 'POST',
        append_segments('autoscale', 'events'),
        # note: if we actually wanted a JSON response instead of XML,
        # we'd have to pass the header:
        # 'accept': ['application/vnd.rackspace.atom+json'],
        headers={
            'content-type': ['application/vnd.rackspace.atom+json']},
        data=event, log=log, success_pred=has_code(201),
        json_response=False)
