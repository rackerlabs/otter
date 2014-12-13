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
from otter.util.http import APIError


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


def effect_on_response(codes, effect, result):
    """
    Returns the specified effect if the resulting HTTP response code is
    in ``codes``.

    Useful for invalidating auth caches if an HTTP response is an auth-related
    error.

    :param tuple codes: integer HTTP codes
    :param effect: An Effect to perform when response code is in ``codes``.
    :param result: The result to inspect, from an Effect of :obj:`Request`.
    """
    response, content = result
    if response.code in codes:
        return effect.on(success=lambda ignored: result)
    else:
        return result


def check_status(success_codes, result):
    """Ensure that the response code is acceptable. If not, raise APIError."""
    response, content = result
    if response.code not in success_codes:
        raise APIError(response.code, content, response.headers)
    return result


def has_code(*codes):
    """
    Return a response success predicate that checks the status code.

    :param codes: Status codes to be considered successful.
    :type codes: ints
    :return: Response success predicate that checks for these codes.
    :rtype: function
    """
    def check_response_code(response, _content):
        """
        Checks if the given response has a successful error code.

        :param response: Response object, from treq.
        :return: :data:`True` if the error code indicates success,
            :data:`False` otherwise.
        :rtype: bool
        """
        return response.code in codes
    return check_response_code


# Request function decorators! These make up the most common API exposed by this
# module.

# The request_func is the last argument of each function, for two reasons
# 1. allows them to be used as decorators with @partial(foo, extra_args)
# 2. it makes big nested constructs of wrappers cleaner, e.g.
#       add_effect_on_response(
#           invalidate_auth_effect, codes,
#           add_effectful_headers(auth_headers_effect, request))
#    because the arguments for a function are closer to that function's name.

def add_effectful_headers(headers_effect, request_func):
    """
    Decorate a request function so that headers are added based on an
    Effect. Useful for authentication.
    """
    @wraps(request_func)
    def request(*args, **kwargs):
        headers = kwargs.pop('headers', {})
        headers = headers if headers is not None else {}

        def got_additional_headers(additional_headers):
            return request_func(*args,
                                headers=merge(headers, additional_headers),
                                **kwargs)
        return headers_effect.on(got_additional_headers)
    return request


def add_headers(fixed_headers, request_func):
    """
    Decorate a request function so that some fixed headers are added.

    :param fixed_headers: The headers that will be added to all requests
        made with the resulting request function. These override any
        headers passed to the request function.
    """
    @wraps(request_func)
    def request(*args, **kwargs):
        headers = kwargs.pop('headers', {})
        headers = headers if headers is not None else {}
        return request_func(*args, headers=merge(headers, fixed_headers),
                            **kwargs)
    return request


def add_effect_on_response(effect, codes, request_func):
    """
    Decorate a request function so an effect is invoked upon receipt of
    specific HTTP response codes as per :func:`effect_on_response`. Useful
    for invalidating authentication caches.
    """
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        partial(effect_on_response, codes, effect))
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
    """
    Decorate a request function so that it parses JSON responses.

    If the body is empty, will make the body :data`None`, and not attempt to
    parse it with a JSON parser, since that would produce an exception.
    """
    request = lambda *args, **kwargs: request_func(*args, **kwargs).on(
        lambda r: (r[0], json.loads(r[1]) if r[1] else None))
    return wraps(request_func)(request)


def add_json_request_data(request_func):
    """
    Decorate a request function so that it JSON-serializes the request body.
    """
    @wraps(request_func)
    def request(*args, **kwargs):
        data = kwargs.pop('data')
        return request_func(*args,
                            data=json.dumps(data) if data is not None else None,
                            **kwargs)
    return request


def add_bind_root(root, request_func):
    """
    Decorate a request function so that it's URL is appended to a common root.
    The URL given is expected to be quoted if required. This decorator does not
    quote the URL.
    """
    if isinstance(root, unicode):
        root = root.encode('ascii')

    @wraps(request_func)
    def request(method, url, *args, **kwargs):
        if isinstance(url, unicode):
            url = url.encode('utf-8')
        url = '{}/{}'.format(root.rstrip('/'), url)
        return request_func(method, url, *args, **kwargs)

    return request
