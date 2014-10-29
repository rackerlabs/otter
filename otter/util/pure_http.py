"""
Purely functional HTTP client.
"""

import json

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


def invalidate_auth_on_error(reauth_codes, invalidate_auth, result):
    """
    Invalidates an auth cache if an HTTP response is an auth-related error.

    :param tuple reauth_codes: integer HTTP codes which should cause an auth
        invalidation.
    :param invalidate_auth: An Effect that invalidates any cached auth
        information that :func:`authenticate_request`'s' ``auth_headers_effect``
        provides.
    :param result: The result to inspect, from an Effect of :obj:`Request`.
    """
    response, content = result
    if response.code in reauth_codes:
        return invalidate_auth.on(success=lambda ignored: result)
    else:
        return result


def check_status(success_codes, result):
    """Ensure that the response code is acceptable. If not, raise APIError."""
    response, content = result
    if response.code not in success_codes:
        raise APIError(response.code, content, response.headers)
    return result


# Request function decorators! These make up the most common API exposed by this
# module.

# The request_func is the last argument of each function, for two reasons
# 1. allows them to be used as decorators with @partial(foo, extra_args)
# 2. it makes big nested constructs of wrappers cleaner, e.g.
#       add_auth_invalidation(
#           invalidate_effect, reauth_codes,
#           add_authentication(auth_headers_effect, request))
#    because the arguments for a function are closer to that function's name.

def add_authentication(auth_headers_effect, request_func):
    """
    Decorate a request function with authentication as per
    :func:`authenticate_request`.
    """
    @wraps(request_func)
    def request(method, url, headers=None, data=None):
        headers = headers if headers is not None else {}

        def got_auth_headers(auth_headers):
            return request_func(method, url,
                                headers=merge(headers, auth_headers),
                                data=data)
        return auth_headers_effect.on(got_auth_headers)
    return request


def add_auth_invalidation(invalidate_effect, reauth_codes, request_func):
    """
    Decorate a request function with auth invalidation as per
    :func:`invalidate_auth_on_error`.
    """
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        partial(invalidate_auth_on_error, reauth_codes, invalidate_effect))
    return wraps(request_func)(request)


def add_error_handling(success_codes, request_func):
    """
    Decorate a request function with response-code checking as per
    :func:`check_status`.
    """
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        partial(check_status, success_codes))
    return wraps(request_func)(request)


def add_content_only(request_func):
    """
    Decorate a request function so that it only returns content, not response
    object.

    This should be the last decorator added, since it changes the shape of
    the result object from a (response, content) to a single string of content.
    """
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        lambda r: r[1])
    return wraps(request_func)(request)


def add_json_response(request_func):
    """Decorate a request function so that it parses JSON responses."""
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        lambda r: (r[0], json.loads(r[1])))
    return wraps(request_func)(request)


def add_json_request_data(request_func):
    """
    Decorate a request function so that it JSON-serializes the request body.
    """
    request = lambda method, url, data=None, headers=None: (
        request_func(method, url,
                     data=json.dumps(data) if data is not None else None,
                     headers=headers))
    return wraps(request_func)(request)


def add_bind_root(root, request_func):
    """
    Decorate a request function so that it's URL is appended to a common root.
    """
    request = lambda method, url, *args, **kwargs: (
        request_func(method, append_segments(root, url), *args, **kwargs))
    return wraps(request_func)(request)
