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


def get_links(tenant_id, group_id=None, format="json", api_version="1.0"):
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

    :param link_blob":
    """
    api = "v{0}".format(api_version)
    path_parts = [get_url_root(), api, tenant_id, "autoscale"]
    if group_id is not None:
        path_parts.append(group_id)

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
