"""
HTTP utils, such as formulation of URLs
"""

from itertools import chain
from urllib import quote

import treq


def append_segments(uri, *segments):
    """
    Append segments to URI in a reasonable way.

    :param str or unicode uri: base URI with or without a trailing /.
        If uri is unicode it will be encoded as ascii.  This is not strictly
        correct but is probably fine since all these URIs are coming from JSON
        and should be properly encoded.  We just need to make them str objects
        for Twisted.
    :type segments: str or unicode
    :param segments: One or more segments to append to the base URI.

    :return: complete URI as str.
    """
    def _segments(segments):
        for s in segments:
            if isinstance(s, unicode):
                s = s.encode('utf-8')

            yield quote(s)

    if isinstance(uri, unicode):
        uri = uri.encode('ascii')

    uri = '/'.join(chain([uri.rstrip('/')], _segments(segments)))
    return uri


class APIError(Exception):
    """
    An error raised when a non-success response is returned by the API.

    :param int code: HTTP Response code for this error.
    :param str body: HTTP Response body for this error or None.
    """
    def __init__(self, code, body):
        Exception.__init__(
            self,
            'API Error code={0!r}, body={1!r}'.format(code, body))

        self.code = code
        self.body = body


def check_success(response, success_codes):
    """
    Convert an HTTP response to an appropriate APIError if
    the response code does not match an expected success code.

    This is intended to be used as a callback for a deferred that fires with
    an IResponse provider.

    :param IResponse response: The response to check.
    :param list success_codes: A list of int HTTP response codes that indicate
        "success".

    :return: response or a deferred that errbacks with an APIError.
    """
    def _raise_api_error(body):
        raise APIError(response.code, body)

    if response.code not in success_codes:
        return treq.content(response).addCallback(_raise_api_error)

    return response


def headers(auth_token=None):
    """
    Generate an appropriate set of headers given an auth_token.

    :param str auth_token: The auth_token or None.
    :return: A dict of common headers.
    """
    h = {'content-type': ['application/json'],
         'accept': ['application/json']}

    if auth_token is not None:
        h['x-auth-token'] = [auth_token]

    return h
