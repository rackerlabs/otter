"""
Publishing events to Cloud feeds
"""

import uuid
from copy import deepcopy
from functools import partial

from characteristic import attributes

from effect import Effect, Func

from toolz.dicttoolz import keyfilter

from twisted.python.log import addObserver

from txeffect import perform

from otter.cloud_client import TenantScope, service_request
from otter.constants import ServiceType
from otter.effect_dispatcher import get_full_dispatcher
from otter.log import log as otter_log
from otter.log.formatters import (
    ErrorFormattingWrapper, LogLevel, PEP3101FormattingWrapper)
from otter.log.intents import err as err_effect, msg as msg_effect
from otter.log.spec import SpecificationObserverWrapper
from otter.util.http import append_segments
from otter.util.pure_http import has_code
from otter.util.retry import (
    exponential_backoff_interval,
    retry_effect,
    retry_times)
from otter.util.timestamp import epoch_to_utctimestr


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


def cf_msg(msg, **fields):
    """
    Helper function to log cloud feeds event
    """
    return msg_effect(msg, cloud_feed=True, **fields)


def cf_err(msg, **fields):
    """
    Log cloud feed error event without failure
    """
    return msg_effect(msg, isError=True, cloud_feed=True, **fields)


def cf_fail(failure, msg, **fields):
    """
    Log cloud feed error event with failure
    """
    return err_effect(failure, msg, cloud_feed=True, **fields)


def sanitize_event(event):
    """
    Sanitize event by removing all items except the ones in autoscale schema.

    :param dict event: Event to sanitize as given by Twisted

    :return: (dict, bool, str) tuple where dict -> sanitized event,
        bool -> is it error event?, str -> ISO8601 formatted UTC time of event
    """
    cf_event = {}
    error = False

    # Get message
    cf_event["message"] = event["message"][0]

    # map keys in event to CF keys
    for log_key, cf_key in log_cf_mapping.iteritems():
        if log_key in event and log_key != 'message':
            cf_event[cf_key] = event[log_key]

    if event["level"] == LogLevel.ERROR:
        error = True
        if ('traceback' in cf_event['message'] or
           'exception' in cf_event['message']):
            raise UnsuitableMessage(cf_event['message'])

    return (cf_event, error, epoch_to_utctimestr(event["time"]))


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


def prepare_request(req_fmt, event, error, timestamp, region, _id):
    """
    Prepare request based on request format
    """
    request = deepcopy(req_fmt)
    if error:
        request['entry']['content']['event']['type'] = 'ERROR'
    request['entry']['content']['event']['region'] = region
    request['entry']['content']['event']['eventTime'] = timestamp
    request['entry']['content']['event']['product'].update(event)
    request['entry']['content']['event']['id'] = _id
    return request


def add_event(event, tenant_id, region, log):
    """
    Add event to cloud feeds
    """
    event, error, timestamp = sanitize_event(event)
    eff = Effect(Func(uuid.uuid4)).on(str).on(
        partial(prepare_request, request_format, event,
                error, timestamp, region))

    def _send_event(req):
        eff = retry_effect(
            service_request(
                ServiceType.CLOUD_FEEDS, 'POST',
                append_segments('autoscale', 'events'),
                headers={
                    'content-type': ['application/vnd.rackspace.atom+json']},
                data=req, log=log, success_pred=has_code(201)),
            retry_times(5), exponential_backoff_interval(2))
        return Effect(TenantScope(tenant_id=tenant_id, effect=eff))

    return eff.on(_send_event)


@attributes(['reactor', 'authenticator', 'tenant_id', 'region',
             'service_configs', 'log', 'get_disp', 'add_event'],
            defaults={'log': otter_log, 'get_disp': get_full_dispatcher,
                      'add_event': add_event})
class CloudFeedsObserver(object):
    """
    Log observer that pushes events to cloud feeds
    """

    def __call__(self, event_dict):
        """
        Process event and push it to Cloud feeds
        """
        if not event_dict.get('cloud_feed', False):
            return
        # Do further logging without cloud_feed to avoid coming back here
        # in infinite recursion
        log_keys = keyfilter(
            lambda k: k not in ('message', 'cloud_feed'), event_dict)
        log = self.log.bind(
            system='otter.cloud_feed', cf_msg=event_dict['message'][0],
            event_data=log_keys)
        try:
            eff = self.add_event(event_dict, self.tenant_id, self.region, log)
        except UnsuitableMessage as me:
            log.err(None, 'cf-unsuitable-message',
                    unsuitable_message=me.unsuitable_message)
        else:
            return perform(
                self.get_disp(self.reactor, self.authenticator, log,
                              self.service_configs),
                eff).addErrback(log.err, 'cf-add-failure')


def add_cf_observer(reactor, authenticator, tenant_id, region,
                    service_configs):
    """
    Add cloud feeds observer after setting up some intial formatting
    """
    cf_observer = CloudFeedsObserver(
        reactor=reactor, authenticator=authenticator, tenant_id=tenant_id,
        region=region, service_configs=service_configs)
    addObserver(
        SpecificationObserverWrapper(
            PEP3101FormattingWrapper(
                ErrorFormattingWrapper(cf_observer))))
