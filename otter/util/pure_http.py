"""
Purely functional HTTP client.
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


def get_request(method, url, **kwargs):
    """Return a Request wrapped in an Effect."""
    return Effect(Request(method=method, url=url, **kwargs))


def request_with_auth(get_request, method, url, auth=None,
                      headers=None, reauth_codes=(401, 403),
                      **kwargs):
    """
    Create an authenticated request. If the request fails with an auth-related
    error, a fresh token will be requested automatically.

    The given 'auth' argument should be a function that returns an Effect of
    authentication headers to add to the request. Before the request is made,
    the auth function will be called with no arguments to get the auth token to
    be used (which may be cached). If the application request fails with an
    auth-related error, the auth function will be invoked again, with a
    refresh=True argument. In this case, new authentication information should
    be retrieved from the authentication service, if necessary.

    If refreshing auth information returns successfully, the original response
    will be returned. If it results in an error, that error will be
    propagated.
    """

    def handle_reauth(result):
        response, content = result
        if response.code in reauth_codes:
            return auth(refresh=True).on(success=lambda headers: result)
        else:
            return result

    def try_request(auth_headers):
        req_headers = {} if headers is None else headers
        req_headers = merge(req_headers, auth_headers)
        eff = get_request(method, url, headers=req_headers, **kwargs)
        return eff.on(success=lambda r: handle_reauth(r))

    return auth().on(success=try_request)


def status_check(success_codes, result):
    """Ensure that the response code is acceptable. If not, raise APIError."""
    (response, content) = result
    if response.code not in success_codes:
        raise APIError(response.code, content, response.headers)
    return result


def request_with_status_check(get_request, method, url, success_codes=(200,),
                              **kwargs):
    """Make a request and perform a status check on the response."""
    return get_request(method, url, **kwargs).on(
        success=partial(status_check, success_codes))


def request_with_json(get_request, method, url, data=None, **kwargs):
    """Convert the request body to JSON, and parse the response as JSON."""
    if data is not None:
        data = json.dumps(data)
    return get_request(method, url, data=data, **kwargs).on(
        success=lambda r: (r[0], json.loads(r[1])))


def content_request(effect):
    """Only return the content part of a response."""
    return effect.on(success=lambda r: r[1])


_request = wrappers(
    get_request,
    request_with_auth,
    request_with_status_check,
    request_with_json)
_request = compose(content_request, _request)


def request(method, url, *args, **kwargs):
    """
    Make an HTTP request, with a number of conveniences. Accepts the same
    arguments as :class:`Request`, in addition to these:

    :param tuple success_codes: integer HTTP codes to accept as successful
    :param data: python object, to be encoded with json
    :param auth: a function to be used to retrieve auth tokens
    :param tuple reauth_codes: integer HTTP codes upon which to reauthenticate
    """
    return _request(method, url, *args, **kwargs)
