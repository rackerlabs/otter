"""
HTTP utils, such as formulation of URLs
"""

from itertools import chain
from urllib import quote

import treq


class RequestError(Exception):
    """
    An error that wraps other errors (such a timeout error) that also
    include the URL so we know what we failed to connect to.

    :ivar Failure subFailure: The connection failure that is wrapped
    :ivar str target: some representation of the connection endpoint -
        e.g. a hostname or ip or a url
    :ivar data: extra information that can be included - this will be
        stringified in the ``repr`` and the ``str``, and can be anything
        with a decent string output (``str``, ``dict``, ``list``, etc.)
    """
    def __init__(self, failure, url, data=None):
        super(RequestError, self).__init__(failure, url)
        self.subFailure = failure
        self.url = url
        self.data = data

    def __repr__(self):
        """
        The ``repr`` of :class:`RequestError` includes the ``repr`` of the
        wrapped failure's exception and the target
        """
        return "RequestError[{0}, {1!r}, data={2!s}]".format(
            self.url, self.subFailure.value, self.data)

    def __str__(self):
        """
        The ``str`` of :class:`RequestError` includes the ``str`` of the
        wrapped failure and the target
        """
        return "RequestError[{0}, {1!s}, data={2!s}]".format(
            self.url, self.subFailure, self.data)


def wrap_request_error(failure, target, data=None):
    """
    Some errors, such as connection timeouts, aren't useful becuase they don't
    contain the url that is timing out, so wrap the error in one that also has
    the url.
    """
    raise RequestError(failure, target, data)


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
