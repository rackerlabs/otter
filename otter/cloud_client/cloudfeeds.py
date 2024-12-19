"""
Cloud feeds related APIs
"""

from otter.cloud_client import service_request
from otter.constants import ServiceType
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
