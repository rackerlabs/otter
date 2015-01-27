"""
Ingesting events to Cloud feeds
"""

import uuid
from copy import deepcopy

from characteristic import attributes

from effect import Effect, perform

from otter.constants import ServiceType
from otter.effect_dispatcher import get_full_dispatcher
from otter.http import TenantScope, service_request
from otter.log import log as otter_log
from otter.util.http import append_segments
from otter.util.pure_http import has_code
from otter.util.retry import (
    exponential_backoff_interval,
    retry_effect,
    retry_times)


# Global single cloud feeds instance
_cloud_feeds = None


def set_cloud_feeds(cf):
    """
    Set single global cloud feed instance
    """
    global _cloud_feeds
    _cloud_feeds = cf


@attributes(['reactor', 'authenticator', 'region', 'tenant_id',
             'service_configs'])
class CloudFeeds(object):
    """
    A placeholder for cloud feeds config
    """


class UnsuitableMessage(Exception):
    """
    Raised when message is not suitable to be pushed to cloud feed
    """
    def __init__(self, message):
        self.unsuitable_message = message


# Mapping of items in a log event to cloud feeds event
log_cf_mapping = {
    "scaling_group_id": "scalingGroupId",
    "policy_id": "policyId",
    "webhook_id": "webhookId",
    "username": "username",
    "desired_capacity": "desiredCapacity",
    "current_capacity": "currentCapacity",
    "message": "message"
}


def sanitize_event(event):
    """
    Sanitize event by removing all items except the ones in autoscale schema.

    :param dict event: Event to sanitize

    :return: Sanitized CF formatted event
    """
    cf_event = {}
    error = False

    # map keys in event to CF keys
    for log_key, cf_key in log_cf_mapping.iteritems():
        if log_key in event:
            cf_event[cf_key] = event[log_key]

    if event.get('isError', False):
        error = True
        if ('traceback' in cf_event['message'] or
           'exception' in cf_event['message']):
            raise UnsuitableMessage(cf_event['message'])

    return cf_event, error


request_format = {
    "entry": {
        "@type": "http://www.w3.org/2005/Atom",
        "title": "autoscale",
        "content": {
            "event": {
                "@type": "http://docs.rackspace.com/core/event",
                "id": "",
                "version": "2",
                "eventTime": "",
                "type": "INFO",
                "region": "",
                "product": {
                    "@type": "http://docs.rackspace.com/event/autoscale",
                    "serviceCode": "Autoscale",
                    "version": "1",
                    "message": ""
                }
            }
        }
    }
}


def add_event(event, error, timestamp, region, log, _uuid=uuid.uuid4):
    """
    Add event to cloud feeds
    """
    request = deepcopy(request_format)
    if error:
        request['entry']['content']['event']['type'] = 'ERROR'
    request['entry']['content']['event']['region'] = region
    request['entry']['content']['event']['eventTime'] = timestamp
    request['entry']['content']['event']['product'].update(event)
    request['entry']['content']['event']['id'] = str(_uuid())
    return retry_effect(
        service_request(
            ServiceType.CLOUD_FEEDS, 'POST',
            append_segments('autoscale', 'events'), data=request,
            log=log, success_pred=has_code(201)),
        retry_times(5), exponential_backoff_interval(2))


def add_event_to_cloud_feed(event, timestamp, log=otter_log,
                            get_disp=get_full_dispatcher):
    """
    Add event to cloud feed by sanityzing it first

    :param dict event: Event dict as it would be passed to observer
    :param str timestamp: ISO8601 formatted timestamp of the event
    """
    cf = _cloud_feeds
    # Take out cloud_feed to avoid coming back here in infinite recursion
    event.pop('cloud_feed', None)
    log = log.bind('otter.cloud_feed', **event)
    try:
        event, error = sanitize_event(event)
    except UnsuitableMessage as me:
        log.err(me, ('Tried to add unsuitable message in cloud feeds: '
                     '{unsuitable_message}'),
                unsuitable_message=me.unsuitable_message)
    else:
        eff = Effect(TenantScope(cf.tenant_id,
                                 add_event(event, error, timestamp,
                                           cf.region, log)))
        # TODO: Log error if event was not added
        perform(
            get_disp(cf.reactor, cf.authenticator, cf.log,
                     cf.service_configs),
            eff)
