"""
Integration point for HTTP clients in otter.
"""
import json
from functools import partial, wraps

from effect import Effect, FuncIntent

from otter.util.pure_http import (
    get_request, request_with_auth, check_status, bind_root)
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
    def unsafe_auth():
        d = authenticator.authenticate_tenant(tenant_id, log=log)
        return d.addCallback(lambda r: r[0])
    unsafe_invalidate = partial(authenticator.invalidate, tenant_id)
    auth_headers = Effect(FuncIntent(unsafe_auth)).on(success=headers)
    invalidate = Effect(FuncIntent(unsafe_invalidate))
    default_log = log

    def request(method, url, headers=None, data=None, log=default_log,
                reauth_codes=(401, 403),
                success_codes=(200,)):
        # TODO: We may want to parameterize some retry options *here*, but only
        # if it's really necessary.
        """
        Make an HTTP request, with a bunch of awesome behavior!

        :param bytes method: as :func:`get_request`.
        :param url: as :func:`get_request`.
        :param dict headers: as :func:`get_request`, but will have
            authentication headers added.
        :param data: JSON-able object.
        :param log: as :func:`get_request`.
        :param sequence success_codes: HTTP codes to consider successful.
        :param sequence reauth_codes: HTTP codes upon which to invalidate the
            auth cache.

        :raise APIError: When the response HTTP code is not in success_codes.
        :return: JSON-parsed object.
        """
        data = json.dumps(data) if data is not None else None
        request_with_headers = lambda h: get_request(method, url, headers=h,
                                                     data=data, log=log)
        return request_with_auth(
            request_with_headers,
            auth_headers,
            invalidate,
            headers=headers,
            reauth_codes=reauth_codes,
        ).on(partial(check_status, success_codes)
             ).on(lambda result: result[1]
                  ).on(json.loads)
    return request


def bind_service(request_func, tenant_id, authenticator, service_name, region,
                 log):
    """
    Bind a request function to a particular Rackspace/OpenStack service and
    tenant.
    """
    # We authenticate_tenant here, which is a duplicate to the one in the
    # underlying request_func, but the authenticators are always caching in
    # practice.
    eff = Effect(FuncIntent(partial(authenticator.authenticate_tenant, tenant_id, log)))

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
            bound_request = bind_root(request_func, endpoint)
            return bound_request(*args, **kwargs)
        return eff.on(got_auth)
    return service_request
