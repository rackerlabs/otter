"""
Integration point for HTTP clients in otter.
"""
from functools import partial, wraps

from effect import Effect, FuncIntent

from otter.util.pure_http import (
    request, add_headers, add_effect_on_response, add_error_handling,
    add_bind_root, add_content_only, add_json_response, add_json_request_data)
from otter.util.http import headers as otter_headers
from otter.worker.launch_server_v1 import public_endpoint_url


def get_request_func(authenticator, tenant_id, log, service_mapping, region):
    """
    Return a pure_http.Request-returning function extended with:

    - authentication for Rackspace APIs
    - HTTP status code checking
    - JSON bodies and return values
    - returning only content of the result, not response objects
    - logging
    :param service_mapping: A mapping of otter.constants.ServiceType constants
        to real service names as found in a tenant's catalog.
    :param region: The region of the Rackspace services which requests will
        be made to.
    """
    def impure_auth():
        return authenticator.authenticate_tenant(tenant_id, log=log)
    impure_invalidate = partial(authenticator.invalidate, tenant_id)
    auth_eff = Effect(FuncIntent(impure_auth))
    invalidate_eff = Effect(FuncIntent(impure_invalidate))
    default_log = log

    @wraps(request)
    def otter_request(service_type, method, url, headers=None, data=None,
                      log=default_log,
                      reauth_codes=(401, 403),
                      success_codes=(200,),
                      json_response=True):
        # TODO: We may want to parameterize some retry options *here*, but only
        # if it's really necessary.
        """
        Make an HTTP request, with a bunch of awesome behavior!

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
                        success_codes,
                        add_effect_on_response(
                            invalidate_eff,
                            reauth_codes,
                            add_headers(otter_headers(token), request)))))
            if json_response:
                request_ = add_json_response(request_)
            request_ = add_content_only(request_)
            return request_(method, url, headers=headers, data=data, log=log)
        return auth_eff.on(got_auth)
    return otter_request


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
