"""
Integration point for HTTP clients in otter.
"""
import re
from functools import partial, wraps

from characteristic import Attribute, attributes

from effect import (
    ComposedDispatcher,
    Effect,
    TypeDispatcher,
    catch,
    perform,
    sync_performer)
from effect.twisted import deferred_performer, perform as twisted_perform

import six

from twisted.internet.defer import DeferredLock
from twisted.internet.task import deferLater

from otter.auth import Authenticate, InvalidateToken, public_endpoint_url
from otter.constants import ServiceType
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
    lock = throttler(service_request.service_type,
                     service_request.method.lower())
    if lock is not None:
        return Effect(_Throttle(bracket=lock, effect=eff))
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


def _make_default_throttler(clock):
    """Get a throttler function with default throttling policies."""
    # Serialize creation and deletion of cloud servers because the Compute team
    # has suggested we do this.
    policy = {
        (ServiceType.CLOUD_SERVERS, 'post'): _serialize_and_delay(clock, 1),
        (ServiceType.CLOUD_SERVERS, 'delete'): _serialize_and_delay(clock, 1),
    }
    return lambda stype, meth: policy.get((stype, meth))


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
    throttler = _make_default_throttler(reactor)
    return TypeDispatcher({
        TenantScope: partial(perform_tenant_scope, authenticator, log,
                             service_configs, throttler),
        _Throttle: partial(_perform_throttle),
    })


# ----- CLB requests and error parsing -----

_CLB_PENDING_UPDATE_PATTERN = re.compile(
    "^Load Balancer '\d+' has a status of 'PENDING_UPDATE' and is considered "
    "immutable.$")
_CLB_DELETED_PATTERN = re.compile(
    "^(Load Balancer '\d+' has a status of 'PENDING_DELETE' and is|"
    "The load balancer is deleted and) considered immutable.$")
_CLB_NO_SUCH_NODE_PATTERN = re.compile(
    "^Node with id #\d+ not found for loadbalancer #\d+$")
_CLB_NO_SUCH_LB_PATTERN = re.compile(
    "^Load balancer not found.$")


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBPendingUpdateError(Exception):
    """
    Error to be raised when the CLB is in PENDING_UPDATE status and is
    immutable (temporarily).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBDeletedError(Exception):
    """
    Error to be raised when the CLB has been deleted or is being deleted.
    This is distinct from it not existing.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class NoSuchCLBError(Exception):
    """
    Error to be raised when the CLB never existed in the first place (or it
    has been deleted so long that there is no longer a record of it).
    """


@attributes([Attribute('lb_id', instance_of=six.text_type),
             Attribute('node_id', instance_of=six.text_type)])
class NoSuchCLBNodeError(Exception):
    """
    Error to be raised when attempting to modify a CLB node that no longer
    exists.
    """


@attributes([Attribute('lb_id', instance_of=six.text_type)])
class CLBRateLimitError(Exception):
    """
    Error to be raised when CLB returns 413 (rate limiting).
    """


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

    :raises: :class:`CLBPendingUpdateError`, :class:`CLBDeletedError`,
        :class:`NoSuchCLBError`, :class:`NoSuchCLBNodeError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_LOAD_BALANCERS,
        'PUT',
        append_segments('loadbalancers', lb_id, 'nodes', node_id),
        data={'condition': condition, 'weight': weight},
        success_pred=has_code(202))

    def _check_no_such_node(api_error_code, json_body):
        if (api_error_code == 404 and _CLB_NO_SUCH_NODE_PATTERN.match(
                json_body.get('message', ''))):
            raise NoSuchCLBNodeError(lb_id=lb_id, node_id=node_id)

    parse_err = partial(_process_clb_api_error, lb_id=lb_id,
                        extra_parsing=_check_no_such_node)

    return eff.on(error=catch(APIError, parse_err))


def _process_clb_api_error(exc_info, lb_id, extra_parsing):
    """
    Attempt to parse generic CLB API error messages, and raise recognized
    exceptions in their place.  If that doesn't work, calls the
    ``extra_parsing`` callable with the HTTP status code, and parsed JSON body.

    If that still doesn't cut it, re-raise the original exception.

    :param string lb_id: The load balancer ID
    :param int api_error_code: The status code from the HTTP request
    :param dict error_json: The error message, parsed as a JSON dict.

    :raises: :class:`CLBPendingUpdateError`, :class:`CLBDeletedError`,
        :class:`NoSuchCLBError`, :class:`APIError` by itself
    """
    api_error = exc_info[1]
    message = try_json_with_keys(api_error.body, ['message'])

    if message:
        if api_error.code == 413:
            raise CLBRateLimitError(message, lb_id=lb_id)

        generic_mappings = [
            (422, _CLB_DELETED_PATTERN, CLBDeletedError),
            (422, _CLB_PENDING_UPDATE_PATTERN, CLBPendingUpdateError),
            (404, _CLB_NO_SUCH_LB_PATTERN, NoSuchCLBError)
        ]
        for status, pattern, exc_type in generic_mappings:
            if status == api_error.code and pattern.match(message):
                raise exc_type(message, lb_id=lb_id)

        # No generic exceptions were raised - try the extra_parsing.
        extra_parsing(api_error.code, try_json_with_keys(api_error.body, []))

    # No? Re-raise, then
    six.reraise(*exc_info)


# ----- Nova requests and error parsing -----

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


@attributes([])
class NovaRateLimitError(Exception):
    """
    Exception to be raised when Nova has rate-limited requests.
    """


_MAX_METADATA_PATTERN = re.compile('^Maximum number of metadata items .*$')


def set_nova_metadata_item(server_id, key, value):
    """
    Set metadata key/value item on the given server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)

    Succeed on 200.

    :raise: :class:`NoSuchServer`, :class:`MetadataOverLimit`,
        :class:`NovaRateLimitError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'PUT',
        append_segments('servers', server_id, 'metadata', key),
        data={'meta': {key: value}},
        reauth_codes=(401,),
        success_pred=has_code(200))

    def _parse_err(exc_info):
        api_error = exc_info[1]
        _check_nova_rate_limit(api_error)

        matches = [
            (404, ('itemNotFound', 'message'), None, NoSuchServerError),
            (403, ('forbidden', 'message'), _MAX_METADATA_PATTERN,
             ServerMetadataOverLimitError),
        ]

        for code, keys, pattern, exc_class in matches:
            if api_error.code == code:
                message = try_json_with_keys(api_error.body, keys)
                if message and (not pattern or pattern.match(message)):
                    raise exc_class(message,
                                    server_id=six.text_type(server_id))

        six.reraise(*exc_info)

    return eff.on(error=catch(APIError, _parse_err))


def get_server_details(server_id):
    """
    Get details for one particular server.

    :ivar str server_id: a Nova server ID.

    Succeed on 200.

    :raise: :class:`NoSuchServer`, :class:`NovaRateLimitError`,
        :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'GET',
        append_segments('servers', server_id),
        success_pred=has_code(200))

    def _parse_err(exc_info):
        api_error = exc_info[1]
        _check_nova_rate_limit(api_error)

        if api_error.code == 404:
            message = try_json_with_keys(api_error.body,
                                         ('itemNotFound', 'message'))
            if message:
                raise NoSuchServerError(message, server_id=server_id)

        six.reraise(*exc_info)

    return eff.on(error=catch(APIError, _parse_err))


def _check_nova_rate_limit(api_error):
    """
    Check if the API error is a nova rate limiting error.
    """
    if api_error.code == 413:
        message = try_json_with_keys(api_error.body, ('overLimit', 'message'))
        if message:
            raise NovaRateLimitError(message)
