"""
Contains the actual Klein app, backing store, and utilities used by the route
handlers for the REST service.
"""
from functools import partial

from twisted.web.resource import Resource
from twisted.web.server import Request
from twisted.web.static import Data

from klein import Klein

from otter.util.http import append_segments
from otter.util.config import config_value


_store = None
_bobby = None

Request.defaultContentType = 'application/json'  # everything should be json


def get_store():
    """
    :return: the store to be used in forming the REST responses
    :rtype: :class:`otter.models.interface.IScalingGroupCollection` provider
    """
    global _store
    if _store is None:
        from otter.models.mock import MockScalingGroupCollection
        _store = MockScalingGroupCollection()
    return _store


def get_url_root():
    """
    Get the URL root
    :return: string containing the URL root
    """
    return config_value('url_root')


def set_store(store):
    """
    Sets the store to use in forming the REST responses

    :param store: the store to be used in forming the REST responses
    :type store: :class:`otter.models.interface.IScalingGroupCollection`
        provider


    :return: None
    """
    global _store
    _store = store


def get_bobby():
    """
    :return: The bobby instance or None
    """
    return _bobby


def set_bobby(bobby):
    """
    Sets the Bobby used in coordination.

    :param bobby: the Bobby instance used in MaaS coordination
    """
    global _bobby
    _bobby = bobby


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


app = Klein()
app.route = partial(app.route, strict_slashes=False)

root = Resource()
root.putChild('v1.0', app.resource())
root.putChild('', Data('', 'text/plain'))
