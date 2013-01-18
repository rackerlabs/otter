"""
Contains the actual Klein app, backing store, and utilities used by the route
handlers for the REST service.
"""

from twisted.web.resource import Resource

from klein import Klein


_store = None
_urlRoot = 'http://127.0.0.1'


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
    global _urlRoot
    return _urlRoot


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


def get_autoscale_links(tenant_id, group_id=None, policy_id=None, format="json",
                        api_version="1.0"):
    """
    Generates links into the autoscale system, based on the ids given.  If
    the format is "json", then a JSON blob will be given in the form of::

        [
          {
            "href": <url with api version>,
            "rel": "self"
          },
          {
            "href": <url without api version>,
            "rel": "bookmark"
          }
        ]

    Otherwise, the return value will just be the link.

    :param tenant_id: the tenant ID of the user
    :type tenant_id: ``str``

    :param group_id: the scaling group UUID - if not provided then the link(s)
        provided will be just the link to listing all scaling groups for the
        tenant ID/creating an autoscale group.
    :type group_id: ``str`` or ``None``

    :param format: whether to return a bunch of links in JSON format
    :type format: ``str`` that should be 'json' if the JSON format is desired

    :param api_version: Which API version to provide links to - generally
        should not be overriden
    :type api_version: ``str``

    :return: JSON blob if `format="json"` is given, a ``str`` containing a link
        else
    """
    api = "v{0}".format(api_version)
    path_parts = [get_url_root(), api, tenant_id, "groups"]
    if group_id is not None:
        path_parts.append(group_id)
        if policy_id is not None:
            path_parts.append("policy")
            path_parts.append(policy_id)

    url = "/".join(path_parts)

    if format == "json":
        return [
            {"href": url, "rel": "self"},
            {"href": url.replace('/{0}/'.format(api), '/'), "rel": "bookmark"}
        ]
    else:
        return url

app = Klein()
root = Resource()
root.putChild('v1.0', app.resource())
