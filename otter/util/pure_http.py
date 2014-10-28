"""
Purely functional HTTP client.
"""
from functools import partial, wraps

from effect import Effect
from characteristic import attributes
from toolz.dicttoolz import merge
from twisted.internet.defer import inlineCallbacks, returnValue

from otter.util import logging_treq
from otter.util.http import APIError, append_segments


@attributes(['method', 'url', 'headers', 'data', 'log'],
            defaults={'headers': None, 'data': None, 'log': None})
class Request(object):
    """
    An effect request for performing HTTP requests.

    The effect results in a two-tuple of (response, content).
    """

    treq = logging_treq

    @inlineCallbacks
    def perform_effect(self, dispatcher):
        """
        Perform the request with treq.

        :return: A two-tuple of (HTTP Response, content as bytes)
        """
        response = yield self.treq.request(self.method.upper(), self.url,
                                           headers=self.headers,
                                           data=self.data, log=self.log)
        content = yield self.treq.content(response)
        returnValue((response, content))


def request(method, url, **kwargs):
    """Return a Request wrapped in an Effect."""
    return Effect(Request(method=method, url=url, **kwargs))


def auth_request(request, auth_headers_effect):
    """
    Authenticates a request, using an effect to produce authentication
    headers.

    :param Request request: the request.
    :param Effect auth_headers_effect: An Effect that results in auth-related
        headers as a dict.
    :return: An :obj:`Effect` of :obj:`Request`, updated with the auth headers.
    """
    def got_auth_headers(auth_headers):
        return Effect(Request(
            method=request.method,
            url=request.url,
            headers=merge(request.headers if request.headers else {},
                          auth_headers),
            data=request.data))
    return auth_headers_effect.on(got_auth_headers)


def invalidate_auth_on_error(reauth_codes, invalidate_auth, result):
    """
    Invalidates an auth cache if an HTTP response is an auth-related error.

    :param tuple reauth_codes: integer HTTP codes which should cause an auth
        invalidation.
    :param invalidate_auth: An Effect that invalidates any cached auth
        information that :func:`auth_request`'s' ``auth_headers_effect``
        provides.
    :param result: The result to inspect, from an Effect of :obj:`Request`.
    """
    response, content = result
    if response.code in reauth_codes:
        return invalidate_auth.on(success=lambda ignored: result)
    else:
        return result


def request_with_auth(request,
                      get_auth_headers,
                      invalidate_auth,
                      reauth_codes=(401, 403)):
    """
    Get a request that will perform book-keeping on cached auth info.

    This composes the :func:`auth_request` and :func:`invalidate_auth_on_error`
    functions.

    :param request: As per :func:`auth_request`
    :param auth_headers: As per :func:`auth_request`
    :param invalidate_auth: As per :func:`invalidate_auth_on_error`
    :param reauth_codes: As per :func:`invalidate_auth_on_error`.
    """
    eff = auth_request(request, get_auth_headers)
    return eff.on(success=partial(invalidate_auth_on_error, reauth_codes,
                                  invalidate_auth))


def check_status(success_codes, result):
    """Ensure that the response code is acceptable. If not, raise APIError."""
    response, content = result
    if response.code not in success_codes:
        raise APIError(response.code, content, response.headers)
    return result


def bind_root(request_func, root):
    """
    Given a request function (similar to :func:`request`), return a new
    request function that only takes a relative path instead of an absolute
    URL.
    """
    @wraps(request_func)
    def request(method, url, *args, **kwargs):
        return request_func(method, append_segments(root, url), *args, **kwargs)
    return request
