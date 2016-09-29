"""
Cloud feeds related APIs
"""

from urlparse import parse_qs, urlparse

from effect.do import do, do_return

from twisted.python.constants import NamedConstant, Names

from otter.cloud_client import service_request
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
    PREVIOUS = NamedConstant()
    NEXT = NamedConstant()


@do
def read_entries(url, params, direction):
    """
    Read feed entries on given direction until it is empty
    """
    if direction == Direction.PREVIOUS:
        direction_link = atom.previous_link
    elif direction == Direction.NEXT:
        direction_link = atom.next_link
    else:
        raise ValueError("Invalid direction")
    all_entries = []
    while True:
        resp, feed_str = yield service_request(
            ServiceType.CLOUD_FEEDS, "GET", url, params=params,
            json_response=False)
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
