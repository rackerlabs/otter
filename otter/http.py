"""
Integration point for HTTP clients in otter.
"""
from functools import wraps

from characteristic import attributes
from effect import ComposedDispatcher, Effect, TypeDispatcher, perform, sync_performer

from otter.util.pure_http import (
    request, add_headers, add_effect_on_response, add_error_handling,
    add_bind_root, add_content_only, add_json_response, add_json_request_data,
    has_code)
from otter.util.http import headers as otter_headers
from otter.auth import public_endpoint_url, Authenticate, InvalidateToken


def get_request_func(authenticator, tenant_id, log, service_mapping, region):
    """
    Deprecated. :func:`service_request` should be used instead.

    Return a pure_http.Request-returning function extended with:

    - authentication for Rackspace APIs
    - HTTP status code checking
    - JSON bodies and return values
    - returning only content of the result, not response objects
    - logging
    - abstraction away from specific endpoints -- requests only need
      to specify an :obj:`otter.constants.ServiceType` and a relative path.

    :param ICachingAuthenticator authenticator: the caching authenticator
    :param tenant_id: tenant ID.
    :param BoundLog log: info about requests will be logged to this.
    :param dict service_mapping: A mapping of otter.constants.ServiceType
        constants to real service names as found in a tenant's catalog.
    :param region: The region of the Rackspace services which requests will
        be made to.
    """
    auth_eff = Effect(Authenticate(authenticator, tenant_id, log))
    invalidate_eff = Effect(InvalidateToken(authenticator, tenant_id))
    default_log = log

    @wraps(request)
    def service_request(service_type, method, url, headers=None, data=None,
                        log=default_log,
                        reauth_codes=(401, 403),
                        success_codes=(200,),
                        json_response=True):
        # TODO: We may want to parameterize some retry options *here*, but only
        # if it's really necessary.
        """
        Make an HTTP request to a Rackspace service, with a bunch of awesome
        behavior!

        :param otter.constants.ServiceType service_type: The service against
            which the request should be made.
        :param bytes method: as :func:`request`.
        :param url: as :func:`request`.
        :param dict headers: as :func:`request`, but will have
            authentication headers added.
        :param data: JSON-able object.
        :param log: as :func:`request`.
        :param sequence success_codes: HTTP codes to consider successful.
        :param sequence reauth_codes: HTTP codes upon which to invalidate the
            auth cache.
        :param bool json_response: Specifies whether the response should be
            parsed as JSON.

        :raise APIError: When the response HTTP code is not in success_codes.
        :return: Effect resulting in a JSON-parsed HTTP response body.
        """
        def got_auth((token, catalog)):
            request_ = add_bind_service(
                catalog,
                service_mapping[service_type],
                region,
                log,
                add_json_request_data(
                    add_error_handling(
                        has_code(*success_codes),
                        add_effect_on_response(
                            invalidate_eff,
                            reauth_codes,
                            add_headers(otter_headers(token), request)))))
            if json_response:
                request_ = add_json_response(request_)
            request_ = add_content_only(request_)
            return request_(method, url, headers=headers, data=data, log=log)
        return auth_eff.on(got_auth)
    return service_request


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
        log=None,
        reauth_codes=(401, 403),
        success_codes=(200,),
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
    :param log: log to send request info to.
    :param sequence success_codes: HTTP codes to consider successful.
    :param sequence reauth_codes: HTTP codes upon which to invalidate the
        auth cache.
    :param bool json_response: Specifies whether the response should be
        parsed as JSON.

    :raise APIError: Raised asynchronously when the response HTTP code is not in
        success_codes.
    :return: Effect of :obj:`ServiceRequest`, resulting in a JSON-parsed HTTP
        response body.
    """
    return Effect(ServiceRequest(
        service_type=service_type,
        method=method,
        url=url,
        headers=headers,
        data=data,
        log=log,
        reauth_codes=reauth_codes,
        success_codes=success_codes,
        json_response=json_response))


@attributes(["service_type", "method", "url", "headers", "data",
             "log", "reauth_codes", "success_codes", "json_response"])
class ServiceRequest(object):
    """
    A request to a Rackspace/OpenStack service.

    Note that this intent does _not_ contain a tenant ID. To specify the tenant
    ID for any tree of effects that might contain a ServiceRequest, wrap the
    effect in a :obj:`TenantScope` intent.
    """


@attributes(['effect', 'tenant_id'], apply_with_init=False)
class TenantScope(object):
    """
    An intent that specifies a tenant for any effect which might make
    :obj:`ServiceRequest`s.

    In other words, something like this::

        perform(dispatcher, TenantScope(Effect(ServiceRequest(...))))

    will make the ServiceRequest bound to the specified tenant.
    """
    def __init__(self, effect, tenant_id):
        self.effect = effect
        self.tenant_id = tenant_id


def perform_tenant_scope(
        authenticator, log, service_mapping, region,
        dispatcher, tenant_scope, box):
    """
    Perform a :obj:`TenantScope` by binding the tenant_id specified in it to
    any :obj:`ServiceRequest` effects that it wraps.

    The first arguments before (dispatcher, tenant_scope, box) are intended
    to be partially applied, and the result is a performer that can be put into
    a dispatcher.
    """

    1 / 0

    def effect_to_box(eff, box):
        return eff.on(box.succeed, box.fail)

    @sync_performer
    def scoped_performer(dispatcher, service_request):
        1 / 0
        return concretize_service_request(
            authenticator, log, service_mapping, region,
            tenant_scope.tenant_id, service_request)

    new_disp = ComposedDispatcher([
        TypeDispatcher({ServiceRequest: scoped_performer}),
        dispatcher])
    perform(new_disp, effect_to_box(tenant_scope.effect, box))


def concretize_service_request(
        authenticator, log, service_mapping, region,
        tenant_id,
        service_request):
    """
    Translate a high-level :obj:`ServiceRequest` into a low-level :obj:`Effect`
    of :obj:`pure_http.Request`.

    :param ICachingAuthenticator authenticator: the caching authenticator
    :param tenant_id: tenant ID.
    :param BoundLog log: info about requests will be logged to this.
    :param dict service_mapping: A mapping of otter.constants.ServiceType
        constants to real service names as found in a tenant's catalog.
    :param region: The region of the Rackspace services which requests will
        be made to.
    """
    auth_eff = Effect(Authenticate(authenticator, tenant_id, log))
    invalidate_eff = Effect(InvalidateToken(authenticator, tenant_id))
    if service_request.log is not None:
        log = service_request.log

    def got_auth((token, catalog)):
        request_ = add_bind_service(
            catalog,
            service_mapping[service_request.service_type],
            region,
            log,
            add_json_request_data(
                add_error_handling(
                    has_code(*service_request.success_codes),
                    add_effect_on_response(
                        invalidate_eff,
                        service_request.reauth_codes,
                        add_headers(otter_headers(token), request)))))
        if service_request.json_response:
            request_ = add_json_response(request_)
        request_ = add_content_only(request_)
        return request_(
            service_request.method,
            service_request.url,
            headers=service_request.headers,
            data=service_request.data,
            log=log)
    return auth_eff.on(got_auth)
