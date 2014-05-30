"""
Pure HTTP utilities.
"""
import copy
import json
import treq

from effect import Effect
from characteristic import attributes

from otter.util.http import APIError, headers


# These should probably be in a different module.
def conj_obj(obj, **new_attrs):
    """Conj[oin] an object with some new attributes, without side-effects."""
    new_obj = copy.copy(obj)
    new_obj.__dict__.update(new_attrs)
    return new_obj


def conj(d, new_fields):
    """Conj[oin] two dicts without side-effects."""
    if d is None:
        d = {}
    if new_fields is None:
        new_fields = {}
    new_d = d.copy()
    new_d.update(new_fields)
    return new_d


@attributes(['method', 'url', 'headers', 'data', 'log'],
            defaults={'headers': None, 'data': None, 'log': None})
class Request(object):
    """
    An effect request for performing HTTP requests.

    The effect results in a two-tuple of (response, content).
    """
    def perform_effect(self, handlers):
        """
        Perform the request with the given treq client.

        :param treq: The treq object.
        """
        func = getattr(treq, self.method)

        def got_response(response):
            result = treq.content(response)
            return result.addCallback(lambda content: (response, content))
        result = func(self.url, headers=self.headers, data=self.data,
                      log=self.log)
        return result.addCallback(got_response)


class ReauthIneffectualError(Exception):
    """
    Raised when an HTTP request returned 401 even after successful
    reauthentication was performed.
    """


class OSHTTPClient(object):
    """
    A slightly higher-level HTTP client, which:
    - includes standard autoscale/openstack headers in requests
    - handles reauthentication when a 401 is received
    - parses JSON responses
    - checks for successful HTTP codes
    """
    def __init__(self, reauth):
        self.reauth = reauth

    def _handle_reauth(self, result, request, success, retries=1):
        response, content = result

        def _got_reauth_result(auth_token):
            return self._request_with_retry(auth_token, request, success,
                                            retries - 1)
        if response.code == 401:
            if retries == 0:
                raise ReauthIneffectualError()
            return self.reauth().on_success(_got_reauth_result)
        else:
            return result

    def _check_success(self, result, success_codes):
        """
        Check if the HTTP response was returned with a particular HTTP code.
        """
        (response, content) = result
        if response.code not in success_codes:
            raise APIError(response.code, content, response.headers)
        return content

    def _request_with_retry(self, auth_token, request, success, retries=1):
        request = conj_obj(request,
                           headers=conj(request.headers, headers(auth_token)))
        return Effect(request).on_success(
            lambda r: self._handle_reauth(r, request, success, retries))

    def json_request(self, auth_token, request, success=(200,)):
        """
        Do a request, check the response code, and parse the JSON result.

        Returns an Effect which results in the parsed json returned by the
        server.

        :param log: A bound log to pass on to the treq client.
        :param method: The HTTP method to invoke.
        :param url: As treq accepts.
        :param headers: As treq accepts.
        :param data: As treq accepts.
        :param list success: The list of HTTP codes to consider successful.
        """
        return (self._request_with_retry(auth_token, request, success)
                    .on_success(lambda r: self._check_success(r, success))
                    .on_success(json.loads))
