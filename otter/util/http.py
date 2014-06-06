"""
HTTP utils, such as formulation of URLs
"""

from itertools import chain
from urllib import quote, urlencode
import json
from urlparse import urlsplit, urlunsplit, parse_qs

import treq

from otter.util.config import config_value


def _extract_error_message(system, body, unparsed):
    """
    Extract readable message from error body received from upstream system
    """
    if system not in ('nova', 'clb', 'identity'):
        raise NotImplementedError
    # NOTE: Since all the above upstream systems return error in similar format,
    # this parses in one way. In future, if the format changes this implementation
    # need to change
    try:
        body = json.loads(body)
        return body[body.keys()[0]]['message']
    except:
        return unparsed


# REVIEW: I started with specific subclasses for each system (nova, clb and identity)
# but they had too much in common. So decided to put stuff in this class itself
class UpstreamError(Exception):
    """
    An upstream system error that wraps more detailed error

    :ivar Failure error: The detailed error being wrapped
    :ivar str system: the upstream system being contacted, eg: nova, clb, identity
    :ivar str operation: the operation being performed
    :ivar str url: some representation of the connection endpoint -
        e.g. a hostname or ip or a url
    """
    def __init__(self, error, system, operation, url=None):
        self.error = error
        self.system = system
        self.operation = operation
        self.url = url
        msg = self.system + ' error: '
        if error.check(APIError):
            self.apierr_message = _extract_error_message(self.system, error.value.body,
                                                         'Could not parse API error body')
            msg += '{} - {}'.format(error.value.code, self.apierr_message)
        else:
            msg += str(error)
        super(UpstreamError, self).__init__(msg)

    @property
    def details(self):
        """
        Return `dict` of all the details within this object
        """
        d = {'system': self.system, 'operation': self.operation, 'url': self.url}
        if self.error.check(APIError):
            e = self.error.value
            d.update({'code': e.code, 'message': self.apierr_message, 'body': e.body,
                      'headers': e.headers})
        return d


def wrap_upstream_error(f, system, operation, url=None):
    """
    Wrap error in UpstreamError
    """
    raise UpstreamError(f, system, operation, url)


def raise_error_on_code(failure, code, error, system, operation, url):
    """
    Raise `error` if given `code` in APIError.code inside failure matches.
    Otherwise `RequestError` is raised with `url` and `data`
    """
    failure.trap(APIError)
    if failure.value.code == code:
        raise error
    raise UpstreamError(failure, system, operation, url)


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
         'accept': ['application/json'],
         'User-Agent': ['OtterScale/0.0']}

    if auth_token is not None:
        h['x-auth-token'] = [auth_token]

    return h


def get_url_root():
    """
    Get the URL root
    :return: string containing the URL root
    """
    return config_value('url_root')


def _pagination_link(url, rel, limit, marker):
    """
    Generates a link dictionary where the href link has (possibly) limit
    and marker query parameters, so long as they are not None.

    :param url: URL of the collection
    :param rel: What to put under 'rel'
    :param limit: pagination limit
    :param marker: the current pagination marker

    :return: ``dict`` containing an href and the rel, the href being a link
        to the collection represented by the url, limit, and marker
    """
    query_params = {}

    if marker is not None:
        query_params = {'marker': marker, 'limit': limit}
    elif limit != (config_value('limits.pagination') or 100):
        query_params['limit'] = limit

    # split_url is a tuple that can't be modified, so listify it
    # (scheme, netloc, path, query, fragment)
    split_url = urlsplit(url)
    mutable_url_parts = list(split_url)

    # update mutable_url_parts with a scheme and netloc if either are missing
    # so that the final URI will always be an absolute URI
    if not (split_url.scheme and split_url.netloc):
        # generate a new absolute URI so that when split, its scheme, netloc,
        # and path parts can be cannabalized
        donor = urlsplit(
            append_segments(get_url_root(), split_url.path.lstrip('/')))

        mutable_url_parts[:3] = [donor.scheme, donor.netloc, donor.path]

    # update the query parameters with new query parameters if necessary
    if query_params:
        query = parse_qs(split_url.query)
        query.update(query_params)
        querystring = urlencode(query, doseq=True)

        # sort alphabetically for easier testing
        mutable_url_parts[3] = '&'.join(sorted(querystring.split('&')))

    url = urlunsplit(mutable_url_parts)
    return {'href': url, 'rel': rel}


def next_marker_by_offset(collection, limit, marker):
    """
    Returns the next marker that is just the current marker offset by the
    length of the collection or the limit, whichever is smaller

    :param collection: an iterable containing the collection to be paginated
    :param limit: the limit on the collection
    :marker: the current marker used to obtain this collection

    :return: the next marker that would be used to fetch the next collection,
        based on the offset from the current marker
    """
    return (marker or 0) + limit


def next_marker_by_id(collection, limit, marker):
    """
    Returns the next marker based on the limit-1 item in the collection

    :param collection: an iterable containing the collection to be paginated
    :param limit: the limit on the collection
    :marker: the current marker used to obtain this collection

    :return: the next marker that would be used to fetch the next collection,
        based on the collection item ids
    """
    return collection[limit - 1]['id']


def get_collection_links(collection, url, rel, limit=None, marker=None,
                         next_marker=None):
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

    :param marker: the current pagination marker

    :param next_marker: a callable that takes the collection, the limit, and
        the current marker, and returns the next marker
    """
    if next_marker is None:
        next_marker = next_marker_by_id

    links = []
    limit = limit or config_value('limits.pagination') or 100
    if rel is not None:
        links.append(_pagination_link(url, rel, limit, marker))
    if len(collection) >= limit:
        links.append(_pagination_link(url, 'next', limit,
                                      next_marker(collection, limit, marker)))
    return links


def get_groups_links(groups, tenant_id, rel='self', limit=None, marker=None):
    """
    Get the links to groups along with 'next' link
    """
    url = get_autoscale_links(tenant_id, format=None)
    return get_collection_links(groups, url, rel, limit, marker)


def get_policies_links(policies, tenant_id, group_id, rel='self', limit=None, marker=None):
    """
    Get the links to groups along with 'next' link
    """
    url = get_autoscale_links(tenant_id, group_id, "", format=None)
    return get_collection_links(policies, url, rel, limit, marker)


def get_webhooks_links(webhooks, tenant_id, group_id, policy_id,
                       rel='self', limit=None, marker=None):
    """
    Get the links to webhooks along with 'next' link
    """
    url = get_autoscale_links(tenant_id, group_id, policy_id, "", format=None)
    return get_collection_links(webhooks, url, rel, limit, marker)


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
