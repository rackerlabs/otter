"""
Pure HTTP utilities.
"""
import copy
import json
from functools import partial

from effect import Effect
from characteristic import attributes
from toolz.dicttoolz import merge

from otter.util import logging_treq
from otter.util.fp import wrappers
from otter.util.http import APIError, headers as otter_headers


@attributes(['method', 'url', 'headers', 'data', 'log'],
            defaults={'headers': None, 'data': None, 'log': None})
class Request(object):
    """
    An effect request for performing HTTP requests.

    The effect results in a two-tuple of (response, content).
    """

    treq = logging_treq

    def perform_effect(self, dispatcher):
        """Perform the request with treq."""

        def got_response(response):
            result = self.treq.content(response)
            return result.addCallback(lambda content: (response, content))
        result = self.treq.request(
            self.method.upper(), self.url, headers=self.headers, data=self.data,
            log=self.log)
        return result.addCallback(got_response)


class ReauthFailedError(Exception):
    """
    Raised when an HTTP request returned 401 even after successful
    reauthentication was performed.
    """


def get_request(method, url, **kwargs):
    """Return a Request wrapped in an Effect."""
    return Effect(Request(method=method, url=url, **kwargs))


def request_with_reauth(get_request, method, url, auth=None,
                        headers=None, **kwargs):
    """Create a request which will reauthenticate upon 401 and retry."""

    def handle_reauth(result, retries):
        response, content = result

        if response.code == 401:
            if retries == 0:
                raise ReauthFailedError()
            return auth(refresh=True).on(
                success=partial(try_request, retries=retries - 1))
        else:
            return result

    def try_request(token, retries=1):
        req_headers = {} if headers is None else headers
        req_headers = merge(req_headers, otter_headers(token))
        eff = get_request(method, url, headers=req_headers, **kwargs)
        return eff.on(success=lambda r: handle_reauth(r, retries))

    return auth().on(success=try_request)


def request_with_status_check(get_request, method, url, success_codes=(200,), **kwargs):
    """Ensure that the response code is acceptable. If not, raise APIError."""

    def check_success(result):
        (response, content) = result
        if response.code not in success_codes:
            raise APIError(response.code, content, response.headers)
        return result
    eff = get_request(method, url, **kwargs)
    return eff.on(success=partial(check_success))


def json_request(get_request, method, url, data=None, **kwargs):
    """Convert the request body to JSON, and parse the response as JSON."""
    if data is not None:
        data = json.dumps(data)
    return get_request(method, url, data=data, **kwargs).on(
        success=lambda r: (r[0], json.loads(r[1])))


def content_request(get_request, method, url, **kwargs):
    """Only return the content part of a response."""
    return get_request(method, url, **kwargs).on(success=lambda r: r[1])


_request = wrappers(get_request, request_with_reauth, request_with_status_check, json_request, content_request)


def request(method, url, *args, **kwargs):
    """
    Make an HTTP request, with a number of conveniences:

    :param success_codes: HTTP codes to accept as successful.
    :param data: python object, to be encoded with json
    :param auth: a function to be used to retrieve auth tokens.
    """
    return _request(method, url, *args, **kwargs)
