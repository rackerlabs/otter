"""A general-ish purpose Rackspace cloud client API, using Effect."""
import json
import re
from functools import partial, wraps
from urlparse import parse_qs, urlparse

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
from toolz.functoolz import identity

from twisted.internet.task import deferLater

from txeffect import deferred_performer, perform as twisted_perform

from otter.auth import Authenticate, InvalidateToken, public_endpoint_url
from otter.constants import ServiceType
from otter.log.intents import msg as msg_effect
from otter.util.config import config_value
from otter.util.http import APIError, append_segments
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
from otter.util.weaklocks import WeakLocks


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
    :return: Effect of :obj:`ServiceRequest`, resulting in a tuple of
        (:obj:`twisted.web.client.Response`,  JSON-parsed HTTP response body).
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
                        service_request.method.lower(),
                        tenant_id)
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


_CFG_NAMES = {
    (ServiceType.CLOUD_SERVERS, 'post'): 'create_server_delay',
    (ServiceType.CLOUD_SERVERS, 'delete'): 'delete_server_delay',
    (ServiceType.RACKCONNECT_V3, 'get'): 'get_rcv3_delay',
    (ServiceType.RACKCONNECT_V3, 'post'): 'create_rcv3_delay',
    (ServiceType.RACKCONNECT_V3, 'delete'): 'delete_rcv3_delay'
}

# Throttling configs where locking is done per-tenant instead of globally
_CFG_NAMES_PER_TENANT = {
    (ServiceType.CLOUD_LOAD_BALANCERS, 'get'): 'get_clb_delay',
    (ServiceType.CLOUD_LOAD_BALANCERS, 'post'): 'post_clb_delay',
    (ServiceType.CLOUD_LOAD_BALANCERS, 'put'): 'put_clb_delay',
    (ServiceType.CLOUD_LOAD_BALANCERS, 'delete'): 'delete_clb_delay',
}


def _default_throttler(locks, clock, stype, method, tenant_id):
    """
    Get a throttler function with throttling policies based on configuration.
    """
    cfg_name = _CFG_NAMES.get((stype, method))
    if cfg_name is not None:
        delay = config_value('cloud_client.throttling.' + cfg_name)
        if delay is not None:
            lock = locks.get_lock((stype, method))
            return partial(lock.run, deferLater, clock, delay)

    # Could be a per-tenant lock
    cfg_name = _CFG_NAMES_PER_TENANT.get((stype, method))
    if cfg_name is not None:
        delay = config_value('cloud_client.throttling.' + cfg_name)
        if delay is not None:
            lock = locks.get_lock((stype, method, tenant_id))
            return partial(lock.run, deferLater, clock, delay)


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
    throttler = partial(_default_throttler, WeakLocks(), reactor)
    return TypeDispatcher({
        TenantScope: partial(perform_tenant_scope, authenticator, log,
                             service_configs, throttler),
        _Throttle: _perform_throttle,
    })


# ----- Logging responses -----


def log_success_response(msg_type, response_body_filter, log_as_json=True,
                         request_body=""):
    """
    :param str msg_type: A string representing the message type of the log
        message
    :param callable response_body_filter: A callable that takes a the response
        body and returns a version of the body that should be logged - this
        should not mutate the original response body.
    :param bool log_as_json: Should the body be logged as JSON string or
        as dict?
    :param str request_body: Optional body of the request sent
    :return: a function that accepts success result from a `ServiceRequest` and
        log the response body.  This assumes a JSON response, which is a
        tuple of (response, response_content).  (non-JSON responses do not
        currently include the original response)
    """
    def _log_it(result):
        resp, json_body = result
        # So we can link it to any non-cloud_client logs
        request_id = resp.request.headers.getRawHeaders(
            'x-otter-request-id', [None])[0]
        resp_body = (
            json.dumps(response_body_filter(json_body), sort_keys=True)
            if log_as_json else json_body)
        eff = msg_effect(
            msg_type,
            method=resp.request.method,
            url=resp.request.absoluteURI,
            request_body=request_body,
            response_body=resp_body,
            request_id=request_id)
        return eff.on(lambda _: result)

    return _log_it


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


def match_errors(code_keys_exc_mapping, status_code, response_dict):
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


def only_json_api_errors(f):
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


def regex(pattern):
    """
    Compile a case-insensitive pattern.
    """
    return re.compile(pattern, re.I)


# ----- Nova requests and error parsing -----

def _forbidden_plaintext(message):
    return regex(
        "403 Forbidden\s+Access was denied to this resource\.\s+({0})\s*$"
        .format(message))

_NOVA_403_NO_PUBLIC_NETWORK = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000\) not allowed")
_NOVA_403_PUBLIC_SERVICENET_BOTH_REQUIRED = _forbidden_plaintext(
    "Networks \(00000000-0000-0000-0000-000000000000,"
    "11111111-1111-1111-1111-111111111111\) required but missing")
_NOVA_403_RACKCONNECT_NETWORK_REQUIRED = _forbidden_plaintext(
    "Exactly 1 isolated network\(s\) must be attached")
_NOVA_403_QUOTA = regex(
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


_MAX_METADATA_PATTERN = regex('Maximum number of metadata items')


def set_nova_metadata_item(server_id, key, value):
    """
    Set metadata key/value item on the given server.

    :ivar str server_id: a Nova server ID.
    :ivar str key: The metadata key to set (<=256 characters)
    :ivar str value: The value to assign to the metadata key (<=256 characters)

    Succeed on 200.

    :return: a `tuple` of (:obj:`twisted.web.client.Response`, JSON `dict`)
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

    @only_json_api_errors
    def _parse_known_errors(code, json_body):
        other_errors = [
            (404, ('itemNotFound', 'message'), None,
             partial(NoSuchServerError, server_id=six.text_type(server_id))),
            (403, ('forbidden', 'message'), _MAX_METADATA_PATTERN,
             partial(ServerMetadataOverLimitError,
                     server_id=six.text_type(server_id))),
        ]
        match_errors(_nova_standard_errors + other_errors, code, json_body)

    return eff.on(error=_parse_known_errors).on(
        log_success_response('request-set-metadata-item', identity))


def get_server_details(server_id):
    """
    Get details for one particular server.

    :ivar str server_id: a Nova server ID.

    Succeed on 200.

    :return: a `tuple` of (:obj:`twisted.web.client.Response`, JSON `dict`)
    :raise: :class:`NoSuchServer`, :class:`NovaRateLimitError`,
        :class:`NovaComputeFaultError`, :class:`APIError`
    """
    eff = service_request(
        ServiceType.CLOUD_SERVERS,
        'GET',
        append_segments('servers', server_id),
        success_pred=has_code(200))

    @only_json_api_errors
    def _parse_known_errors(code, json_body):
        other_errors = [
            (404, ('itemNotFound', 'message'), None,
             partial(NoSuchServerError, server_id=six.text_type(server_id))),
        ]
        match_errors(_nova_standard_errors + other_errors, code, json_body)

    return eff.on(error=_parse_known_errors).on(
        log_success_response('request-one-server-details', identity))


def create_server(server_args):
    """
    Create a server using Nova.

    :ivar dict server_args:  The dictionary to pass to Nova specifying how
        the server should be built.

    Succeed on 202, and only reauthenticate on 401 because 403s may be terminal
    errors.

    :return: a `tuple` of (:obj:`twisted.web.client.Response`, JSON `dict`)
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

    @only_json_api_errors
    def _parse_known_json_errors(code, json_body):
        other_errors = [
            (400, ('badRequest', 'message'), None,
             CreateServerConfigurationError),
            (403, ('forbidden', 'message'), _NOVA_403_QUOTA,
             CreateServerOverQuoteError)
        ]
        match_errors(_nova_standard_errors + other_errors, code, json_body)

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

    def _remove_admin_pass_for_logging(response):
        return {'server': {
            k: v for k, v in response['server'].items() if k != "adminPass"
        }}

    return (eff
            .on(error=catch(APIError, _parse_known_string_errors))
            .on(error=_parse_known_json_errors)
            .on(log_success_response('request-create-server',
                                     _remove_admin_pass_for_logging)))


def list_servers_details_page(parameters=None):
    """
    List a single page of servers details given filtering and pagination
    parameters.

    :ivar dict parameters: A dictionary with pagination information,
        changes-since filters, and name filters.

    Succeed on 200.

    :return: a `tuple` of (:obj:`twisted.web.client.Response`, JSON `dict`)
    :raise: :class:`NovaRateLimitError`, :class:`NovaComputeFaultError`,
        :class:`APIError`
    """
    @only_json_api_errors
    def _parse_known_errors(code, json_body):
        match_errors(_nova_standard_errors, code, json_body)

    return (
        service_request(
            ServiceType.CLOUD_SERVERS,
            'GET', append_segments('servers', 'detail'),
            params=parameters)
        .on(error=_parse_known_errors)
        .on(log_success_response('request-list-servers-details', identity,
                                 log_as_json=False))
    )


def list_servers_details_all(parameters=None):
    """
    List all pages of servers details, starting at the page specified by the
    given filtering and pagination parameters.

    :ivar dict parameters: A dictionary with pagination information,
        changes-since filters, and name filters.

    Succeed on 200.

    :return: a `list` of server details `dict`s
    :raise: :class:`NovaRateLimitError`, :class:`NovaComputeFaultError`,
        :class:`APIError`
    """
    last_link = []

    def continue_(result, servers_so_far=None):
        if servers_so_far is None:
            servers_so_far = []

        _response, body = result
        servers = servers_so_far + body['servers']

        # Only continue if pagination is supported and there is another page
        continuation = [link['href'] for link in body.get('servers_links', [])
                        if link['rel'] == 'next']
        if continuation:
            # blow up if we try to fetch the same link twice
            if last_link and last_link[-1] == continuation[0]:
                raise NovaComputeFaultError(
                    "When gathering server details, got the same 'next' link "
                    "twice from Nova: {0}".format(last_link[-1]))

            last_link[:] = [continuation[0]]
            parsed_query = parse_qs(urlparse(continuation[0]).query)
            return list_servers_details_page(parsed_query).on(
                partial(continue_, servers_so_far=servers))

        return servers

    return list_servers_details_page(parameters).on(continue_)


_nova_standard_errors = [
    (413, ('overLimit', 'message'), None, NovaRateLimitError),
    (500, ('computeFault', 'message'), None, NovaComputeFaultError)
]


# ----- Cloud orchestration requests -----
def list_stacks_all(parameters=None):
    """
    List Heat stacks.

    :param dict parameters: Query parameters to include.

    :return: List of stack details JSON.
    """
    eff = service_request(
        ServiceType.CLOUD_ORCHESTRATION,
        'GET', 'stacks',
        success_pred=has_code(200),
        reauth_codes=(401,),
        params=parameters)

    return (eff.on(log_success_response('request-list-stacks-all', identity))
               .on(lambda (response, body): body['stacks']))


def create_stack(stack_args):
    """
    Create a stack using Heat.

    :param dict stack_args: The dictionary to pass to Heat specifying how the
        stack should be built.

    :return: JSON `dict`
    """
    eff = service_request(
        ServiceType.CLOUD_ORCHESTRATION,
        'POST', 'stacks',
        data=stack_args,
        success_pred=has_code(201),
        reauth_codes=(401,))

    return (eff.on(log_success_response('request-create-stack', identity))
               .on(lambda (response, body): body['stack']))


def check_stack(stack_name, stack_id):
    """
    Check a stack using Heat.

    :param string stack_name: The name of the stack.
    :param string stack_id: The id of the stack.

    :return: `None`
    """
    eff = service_request(
        ServiceType.CLOUD_ORCHESTRATION,
        'POST', append_segments('stacks', stack_name, stack_id, 'actions'),
        data={'check': None},
        success_pred=has_code(200, 201),
        reauth_codes=(401,),
        json_response=False)

    return (eff.on(log_success_response('request-check-stack', identity,
                                        log_as_json=False))
               .on(lambda _: None))


def update_stack(stack_name, stack_id, stack_args):
    """
    Update a stack using Heat.

    :param string stack_name: The name of the stack.
    :param string stack_id: The id of the stack.
    :param dict stack_args: The dictionary to pass to Heat specifying how the
        stack should be updated.

    :return: `None`
    """
    eff = service_request(
        ServiceType.CLOUD_ORCHESTRATION,
        'PUT', append_segments('stacks', stack_name, stack_id),
        data=stack_args,
        success_pred=has_code(202),
        reauth_codes=(401,),
        json_response=False)

    return (eff.on(log_success_response('request-update-stack', identity,
                                        log_as_json=False))
               .on(lambda _: None))


def delete_stack(stack_name, stack_id):
    """
    Delete a stack using Heat.

    :param string stack_name: The name of the stack.
    :param string stack_id: The id of the stack.

    :return: `None`
    """
    eff = service_request(
        ServiceType.CLOUD_ORCHESTRATION,
        'DELETE', append_segments('stacks', stack_name, stack_id),
        success_pred=has_code(204),
        reauth_codes=(401,),
        json_response=False)

    return (eff.on(log_success_response('request-delete-stack', identity,
                                        log_as_json=False))
               .on(lambda _: None))
