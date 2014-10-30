"""
Integration point for HTTP clients in otter.
"""
from functools import partial, wraps

from effect import Effect, FuncIntent

from otter.util.pure_http import (
    request, add_effectful_headers, add_effect_on_response, add_error_handling,
    add_bind_root, add_content_only, add_json_response, add_json_request_data)
from otter.util.http import headers
from otter.worker.launch_server_v1 import public_endpoint_url


def get_request_func(authenticator, tenant_id, log):
    """
    Return a pure_http.Request-returning function extended with:

    - authentication for Rackspace APIs
    - HTTP status code checking
    - JSON bodies and return values
    - returning only content of the result, not response objects
    - logging
    """
    def impure_auth():
        d = authenticator.authenticate_tenant(tenant_id, log=log)
        return d.addCallback(lambda r: r[0])
    impure_invalidate = partial(authenticator.invalidate, tenant_id)
    auth_headers = Effect(FuncIntent(impure_auth)).on(success=headers)
    invalidate = Effect(FuncIntent(impure_invalidate))
    default_log = log

    def otter_request(method, url, headers=None, data=None, log=default_log,
                      reauth_codes=(401, 403),
                      success_codes=(200,)):
        # TODO: We may want to parameterize some retry options *here*, but only
        # if it's really necessary.
        """
        Make an HTTP request, with a bunch of awesome behavior!

        :param bytes method: as :func:`request`.
        :param url: as :func:`request`.
        :param dict headers: as :func:`request`, but will have
            authentication headers added.
        :param data: JSON-able object.
        :param log: as :func:`request`.
        :param sequence success_codes: HTTP codes to consider successful.
        :param sequence reauth_codes: HTTP codes upon which to invalidate the
            auth cache.

        :raise APIError: When the response HTTP code is not in success_codes.
        :return: Effect resulting in a JSON-parsed HTTP response body.
        """
        request_ = add_content_only(
            add_json_request_data(
                add_json_response(
                    add_error_handling(
                        success_codes,
                        add_effect_on_response(
                            invalidate,
                            reauth_codes,
                            add_effectful_headers(auth_headers, request))))))
        return request_(method, url, headers=headers, data=data, log=log)
    return otter_request


def add_bind_service(tenant_id, authenticator, service_name,
                     region, log, request_func):
    """
    Decorate a request function so requests are relative to a particular
    Rackspace/OpenStack endpoint found in the tenant's catalog.
    """
    # We authenticate_tenant here, which is a duplicate to the one in the
    # underlying request_func, but the authenticators are always caching in
    # practice.
    eff = Effect(FuncIntent(lambda: authenticator.authenticate_tenant(tenant_id, log)))

    @wraps(request_func)
    def service_request(*args, **kwargs):
        """
        Perform an HTTP request similar to the request from
        :func:`get_request_func`, with the additional feature of being bound to
        a specific Rackspace/OpenStack service, so that the path can be
        relative to the service endpoint.
        """
        def got_auth((token, catalog)):
            endpoint = public_endpoint_url(catalog, service_name, region)
            bound_request = add_bind_root(endpoint, request_func)
            return bound_request(*args, **kwargs)
        return eff.on(got_auth)
    return service_request
