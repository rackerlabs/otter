"""
Cloud feeds related APIs
"""

from urlparse import parse_qs, urlparse

from effect.do import do, do_return

from toolz.functoolz import identity

from twisted.python.constants import NamedConstant, Names

from otter.cloud_client import log_success_response, service_request
from otter.constants import ServiceType
from otter.indexer import atom
from otter.util.http import append_segments
from otter.util.pure_http import has_code


def publish_autoscale_event(event, log=None):
    """
    Publish event dictionary to autoscale feed
    """
    return service_request(
        ServiceType.CLOUD_FEEDS, 'POST',
        append_segments('autoscale', 'events'),
        # note: if we actually wanted a JSON response instead of XML,
        # we'd have to pass the header:
        # 'accept': ['application/vnd.rackspace.atom+json'],
        headers={
            'content-type': ['application/vnd.rackspace.atom+json']},
        data=event, log=log, success_pred=has_code(201),
        json_response=False)


class Direction(Names):
    """
    Which direction to follow the feeds?
    """
    PREVIOUS = NamedConstant()
    NEXT = NamedConstant()


@do
def read_entries(service_type, url, params, direction, log_msg_type=None):
    """
    Read all feed entries and follow in given direction until it is empty

    :param service_type: Service hosting the feed
    :type service_type: A member of :class:`ServiceType`
    :param str url: CF URL to append
    :param dict params: HTTP parameters
    :param direction: Where to continue fetching?
    :type direction: A member of :class:`Direction`

    :return: (``list`` of :obj:`Element`, last fetched params) tuple
    """
    if direction == Direction.PREVIOUS:
        direction_link = atom.previous_link
    elif direction == Direction.NEXT:
        direction_link = atom.next_link
    else:
        raise ValueError("Invalid direction")

    if log_msg_type is not None:
        log_cb = log_success_response(log_msg_type, identity, False)
    else:
        log_cb = identity

    all_entries = []
    while True:
        resp, feed_str = yield service_request(
            service_type, "GET", url, params=params,
            json_response=False).on(log_cb)
        feed = atom.parse(feed_str)
        entries = atom.entries(feed)
        if entries == []:
            break
        all_entries.extend(entries)
        link = direction_link(feed)
        if link is None:
            break
        params = parse_qs(urlparse(link).query)
    yield do_return((all_entries, params))
