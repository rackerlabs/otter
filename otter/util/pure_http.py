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


def get_request(method, url, **kwargs):
    """Return a Request wrapped in an Effect."""
    return Effect(Request(method=method, url=url, **kwargs))


def auth_request(get_request, get_auth_headers, headers=None):
    """
    Performs an authenticated request, calling a function to get auth headers.

    :param get_request: A function which only accepts a 'headers' argument,
        and returns an :obj:`Effect` of :obj:`Request`.
    :param get_auth_headers: An Effect that returns auth-related headers as a dict.
    """
    headers = headers if headers is not None else {}
    return get_auth_headers.on(
        success=lambda auth_headers: get_request(merge(headers, auth_headers)))


def invalidate_auth_on_error(reauth_codes, invalidate_auth, result):
    """
    Invalidates an auth cache if an HTTP response is an auth-related error.

    :param invalidate_auth: An Effect that invalidates any cached auth
        information that auth_request's get_auth_headers Effect returns.
    :param tuple reauth_codes: integer HTTP codes which should cause an auth
        invalidation.
    """
    response, content = result
    if response.code in reauth_codes:
        return invalidate_auth.on(success=lambda ignored: result)
    else:
        return result


def request_with_auth(get_request,
                      get_auth_headers,
                      invalidate_auth,
                      headers=None, reauth_codes=(401, 403)):
    """
    Get a request that will perform book-keeping on cached auth info.

    This composes the :func:`auth_request` and :func:`invalidate_auth_on_error`
    functions.

    :param get_auth_headers: As per :func:`auth_request`
    :param invalidate_auth: As per :func:`invalidate_auth_on_error`
    :param reauth_codes: As per :func:`invalidate_auth_on_error`.
    """
    eff = auth_request(get_request, get_auth_headers, headers=headers)
    return eff.on(success=partial(invalidate_auth_on_error, reauth_codes,
                                  invalidate_auth))


def check_status(success_codes, result):
    """Ensure that the response code is acceptable. If not, raise APIError."""
    (response, content) = result
    if response.code not in success_codes:
        raise APIError(response.code, content, response.headers)
    return result


def bind_root(request_func, root):
    """
    Given a request function, return a new request function that only takes a
    relative path instead of an absolute URL.
    """
    @wraps(request_func)
    def request(method, url, *args, **kwargs):
        return request_func(method, append_segments(root, url), *args, **kwargs)
    return request
