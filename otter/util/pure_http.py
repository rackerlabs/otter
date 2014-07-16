"""
Pure HTTP utilities.
"""
import json
from functools import partial

from effect import Effect
from characteristic import attributes
from toolz.dicttoolz import merge
from toolz.functoolz import compose
from twisted.internet.defer import inlineCallbacks, returnValue

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

    @inlineCallbacks
    def perform_effect(self, dispatcher):
        """
        Perform the request with treq.

        :return: A two-tuple of (HTTP Response, content as bytes)
        """
        response = yield self.treq.request(self.method.upper(), self.url, headers=self.headers,
                                           data=self.data, log=self.log)
        content = yield self.treq.content(response)
        returnValue((response, content))


class ReauthFailedError(Exception):
    """
    Raised when an HTTP request returned 401 even after successful
    reauthentication was performed.
    """


def get_request(method, url, **kwargs):
    """Return a Request wrapped in an Effect."""
    return Effect(Request(method=method, url=url, **kwargs))


def request_with_auth(get_request, method, url, auth=None,
                      headers=None, reauth_codes=(401, 403),
                      **kwargs):
    """
    Create an authenticated request. If the request fails with an auth-related error,
    a fresh token will be requested automatically.

    The given 'auth' argument should be a function that returns an Effect of the
    auth token to use. Before the request is made, the auth function will be called
    with no arguments to get the auth token to be used (which may be cached). If
    the application request fails with an auth-related error, the auth function will
    be invoked again, with a refresh=True argument. In this case, a new token must
    be retrieved from the authentication server.

    If refreshing an auth token returns successfully, a NoResponseError exception
    will be raised. If it results in an error, that error will be propagated to the
    Effect that this function returns.
    """

    def handle_reauth(result, retries):
        response, content = result

        if response.code in reauth_codes:
            def got_reauth(result):
                raise NoResponseError()
            return auth(refresh=True).on(success=got_reauth)
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


def content_request(result):
    """Only return the content part of a response."""
    return result.on(success=lambda r: r[1])


def retry(func, retries=3, should_retry=None, **kwargs):
    """
    Call an effectful ``func`` with ``**kwargs``. If it fails, call it again,
    up to ``retries`` times, as long as ``should_retry()`` returns an Effect of
    True.

    If ``should_retry`` returns an Effect of False, then None will be returned.
    """

    def _retry():
        return retry(func, retries=retries - 1, should_retry=should_retry, **kwargs)

    eff = func(**kwargs)

    def maybe_retry(retry_allowed):
        if retry_allowed:
            return _retry()
        else:
            return None

    if should_retry is not None:
        eff = eff.on(error=lambda e: should_retry()).on(success=maybe_retry)

_request = wrappers(get_request, request_with_auth, request_with_status_check, json_request)
_request = compose(content_request, _request)
_request = wrappers(_request, retry)


def request(method, url, *args, **kwargs):
    """
    Make an HTTP request, with a number of conveniences:

    :param success_codes: HTTP codes to accept as successful.
    :param data: python object, to be encoded with json
    :param auth: a function to be used to retrieve auth tokens.
    """
    return _request(method, url, *args, **kwargs)
