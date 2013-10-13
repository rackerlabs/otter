"""
HTTP utils, such as formulation of URLs
"""

from itertools import chain
from urllib import quote, urlencode

import treq

from otter.util.config import config_value


class RequestError(Exception):
    """
    An error that wraps other errors (such a timeout error) that also
    include the URL so we know what we failed to connect to.

    :ivar Failure reason: The connection failure that is wrapped
    :ivar str target: some representation of the connection endpoint -
        e.g. a hostname or ip or a url
    :ivar data: extra information that can be included - this will be
        stringified in the ``repr`` and the ``str``, and can be anything
        with a decent string output (``str``, ``dict``, ``list``, etc.)
    """
    def __init__(self, failure, url, data=None):
        super(RequestError, self).__init__(failure, url)
        self.reason = failure
        self.url = url
        self.data = data

    def __repr__(self):
        """
        The ``repr`` of :class:`RequestError` includes the ``repr`` of the
        wrapped failure's exception and the target
        """
        return "RequestError[{0}, {1!r}, data={2!s}]".format(
            self.url, self.reason.value, self.data)

    def __str__(self):
        """
        The ``str`` of :class:`RequestError` includes the ``str`` of the
        wrapped failure and the target
        """
        return "RequestError[{0}, {1!s}, data={2!s}]".format(
            self.url, self.reason, self.data)


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
    :param Headers headers: HTTP Response headers for this error, or None
    """
    def __init__(self, code, body, headers=None):
        Exception.__init__(
            self,
            'API Error code={0!r}, body={1!r}, headers={2!r}'.format(
                code, body, headers))

        self.code = code
        self.body = body
        self.headers = headers


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
        raise APIError(response.code, body, response.headers)

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


def get_url_root():
    """
    Get the URL root
    :return: string containing the URL root
    """
    return config_value('url_root')


def get_collection_links(collection, url, rel, limit=None, marker=None):
    """
    Return links `dict` for given collection like below. The 'next' link is
    added only if number of items in `collection` has reached `limit`

        [
          {
            "href": <url with api version>,
            "rel": "self"
          },
          {
            "href": <url of next link>,
            "rel": "next"
          }
        ]

    :param collection: the collection whose links are required.
    :type collection: list of dict that has 'id' in it

    :param url: URL of the collection

    :param rel: What to put under 'rel'

    :param limit: pagination limit

    :param marker: pagination marker
    """
    limit = limit or config_value('limits.pagination')
    links = []
    if not marker and rel is not None:
        links.append({'href': url, 'rel': rel})
    if len(collection) >= limit:
        query_params = {'limit': limit, 'marker': collection[limit - 1]['id']}
        next_url = "{0}?{1}".format(url, urlencode(query_params))
        links.append({'href': next_url, 'rel': 'next'})
    return links


def get_groups_links(groups, tenant_id, rel='self', limit=None, marker=None):
    """
    Get the links to groups along with 'next' link
    """
    url = get_autoscale_links(tenant_id, format=None)
    return get_collection_links(groups, url, rel, limit, marker)


def get_autoscale_links(tenant_id, group_id=None, policy_id=None,
                        webhook_id=None, capability_hash=None,
                        capability_version="1", format="json",
                        api_version="1.0"):
    """
    Generates links into the autoscale system, based on the ids given.  If
    the format is "json", then a JSON blob will be given in the form of::

        [
          {
            "href": <url with api version>,
            "rel": "self"
          }
        ]

    Otherwise, the return value will just be the link.

    :param tenant_id: the tenant ID of the user
    :type tenant_id: ``str``

    :param group_id: the scaling group UUID - if not provided then the link(s)
        will be just the link to listing all scaling groups for the tenant
        ID/creating an autoscale group.
    :type group_id: ``str`` or ``None``

    :param policy_id: the scaling policy UUID - if not provided (and `group_id`
        is provided)then the link(s) will be just the link to the scaling group,
        and if blank then the link(s) will to listings of all the policies
        for the scaling group.
    :type policy_id: ``str`` or ``None``

    :param webhook_id: the webhook UUID - if not provided (and `group_id` and
        `policy_id` are provided) then the link(s) will be just the link to the
        scaling policy, and if blank then the link(s) will to listings of all
        the webhooks for the scaling policy
    :type webhook_id: ``str`` or ``None``

    :param format: whether to return a bunch of links in JSON format
    :type format: ``str`` that should be 'json' if the JSON format is desired

    :param api_version: Which API version to provide links to - generally
        should not be overriden
    :type api_version: ``str``

    :param capability_hash: a unique value for the capability url
    :type capability_hash: ``str``

    :param capability_version: capability hash generation version - defaults to
        1
    :type capability_version: ``str``

    :return: JSON blob if `format="json"` is given, a ``str`` containing a link
        else
    """
    api = "v{0}".format(api_version)
    segments = [get_url_root(), api, tenant_id, "groups"]

    if group_id is not None:
        segments.append(group_id)
        if policy_id is not None:
            segments.extend(("policies", policy_id))
            if webhook_id is not None:
                segments.extend(("webhooks", webhook_id))

    if segments[-1] != '':
        segments.append('')

    url = append_segments(*segments)

    if format == "json":
        links = [
            {"href": url, "rel": "self"}
        ]

        if capability_hash is not None:
            capability_url = append_segments(
                get_url_root(),
                api,
                "execute",
                capability_version,
                capability_hash, '')

            links.append({"href": capability_url, "rel": "capability"})

        return links
    else:
        return url


def transaction_id(request):
    """
    Extract the transaction id from the given request.

    :param IRequest request: The request we are trying to get the
        transaction id for.

    :returns: A string transaction id.
    """
    return request.responseHeaders.getRawHeaders('X-Response-Id')[0]
