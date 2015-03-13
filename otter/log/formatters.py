"""
Composable log observers for use with Twisted's log module.
"""
import json
import time
from datetime import datetime

from pyrsistent import pmap

from twisted.python.failure import Failure


class LoggingEncoder(json.JSONEncoder):
    """
    A JSONEncoder that will decide how to serialize objects that the base
    JSONEncoder does not know about. It defaults to repr(obj) when it does not
    know about the object

    This will ensure that even log messages that include unserializable objects
    (like from 3rd party libraries) will still have reasonable representations
    in the logged JSON and will actually be logged and not discarded by the
    logging system because of a formatting error.
    """
    serializers = [(datetime, lambda obj: obj.isoformat()),
                   (Failure, str)]

    def default(self, obj):
        """
        Serialize obj using `serializers` above and fallback to repr
        """
        for _type, serializer in self.serializers:
            if isinstance(obj, _type):
                return serializer(obj)
        return repr(obj)


def JSONObserverWrapper(observer, **kwargs):
    """
    Create an observer that will format the eventDict as JSON using the
    supplied keyword arguments and delegate to `observer`.

    :param ILogObserver observer: The observer to delegate message delivery to.

    :rtype: :class:`ILogObserver`
    """
    def JSONObserver(eventDict):
        if 'message' in eventDict:
            eventDict['message'] = ''.join(eventDict['message'])
        observer({'message': (json.dumps(eventDict,
                                         cls=LoggingEncoder, **kwargs),)})

    return JSONObserver


def StreamObserverWrapper(stream, delimiter='\n', buffered=False):
    """
    Create a log observer that will write bytes to the specified stream.

    :param str or None delimter: A delimiter for each message.
    :param bool buffered: True if output should be buffered, if False we will
        call `flush` on the `stream` after writing every message.

    :rtype: :class:`ILogObserver`
    """
    def StreamObserver(eventDict):
        stream.write(''.join(eventDict['message']))

        if delimiter is not None:
            stream.write(delimiter)

        if not buffered:
            stream.flush()

    return StreamObserver


def SystemFilterWrapper(observer):
    """
    Normalize the system key in the eventDict to not leak strange
    internal twisted system values to the world.

    :param ILogObserver observer: The log observer to delegate to after
        fixing system.

    :rtype: :class:`ILogObserver`
    """
    def SystemFilterObserver(eventDict):
        system = eventDict['system']

        if system == '-':  # No system.
            system = 'otter'
        elif ',' in system:  # This is likely one of the tcp.Server/Client contexts.
            eventDict['log_context'] = system
            system = 'otter'

        eventDict['system'] = system
        observer(eventDict)

    return SystemFilterObserver


def PEP3101FormattingWrapper(observer):
    """
    Format messages using PEP3101 format strings.

    :param ILogObserver observer: The log observer to delegate to after
        formatting message.

    :rtype: :class:`ILogObserver`
    """
    def PEP3101FormattingObserver(eventDict):
        if eventDict.get('why'):
            eventDict['why'] = eventDict['why'].format(**eventDict)

        if 'message' in eventDict:
            message = ' '.join(eventDict['message'])

            if message:
                try:
                    eventDict['message'] = (message.format(**eventDict),)
                except:
                    failure = Failure()
                    eventDict['message_formatting_error'] = str(failure)
                    eventDict['message'] = message

        observer(eventDict)

    return PEP3101FormattingObserver


ERROR_FIELDS = {"isError", "failure", "why"}

PRIMITIVE_FIELDS = {"time", "system", "id", "audit_log", "message"}

AUDIT_LOG_FIELDS = {
    "audit_log": bool,
    "message": basestring,
    "request_ip": basestring,
    "user_id": basestring,
    "tenant_id": basestring,
    "scaling_group_id": basestring,
    "policy_id": basestring,
    "webhook_id": basestring,
    "data": dict,
    "transaction_id": basestring,
    "event_type": basestring,
    "is_error": bool,
    "desired_capacity": int,
    "pending_capacity": int,
    "current_capacity": int,
    "previous_desired_capacity": int,
    "fault": dict,
    "parent_id": basestring,
    "as_user_id": basestring,
    "convergence_delta": int,
    "server_id": basestring,
}


def audit_log_formatter(eventDict, timestamp, hostname):
    """
    Format an eventDict into another dictionary that conforms to the audit log
    format.

    :param dict eventDict: an eventDict as would be passed into an observer
    :param timestamp: a timestamp to use in the timestamp field

    :returns: an audit-log formatted dictionary
    """
    audit_log_params = {
        "@version": 1,
        "@timestamp": timestamp,
        "host": hostname,
        "is_error": False
    }

    for key, value in eventDict.iteritems():
        if key in AUDIT_LOG_FIELDS and isinstance(value, AUDIT_LOG_FIELDS[key]):
                audit_log_params[key] = value

    if "message" not in audit_log_params:
        audit_log_params["message"] = " ".join([
            str(m) for m in eventDict["message"]])

    if eventDict.get("isError", False):
        audit_log_params["is_error"] = True

        # create the fault dictionary, if it doesn't exist, without clobbering
        # any existing details
        fault = {'details': {}}
        fault.update(audit_log_params.get('fault', {}))
        audit_log_params['fault'] = fault

        if 'failure' in eventDict:
            # Do not clobber any details already in there
            fault['details'].update(getattr(eventDict['failure'].value,
                                            'details', {}))

            if 'message' not in fault:
                fault['message'] = eventDict['failure'].value.message

        audit_log_params["message"] = 'Failed: {0}.'.format(
            audit_log_params["message"])

        if 'why' in eventDict and eventDict['why']:
            audit_log_params["message"] = '{0} {1}'.format(
                audit_log_params["message"], eventDict['why'])

        # strip out any repeated info in the details dict
        delete = []
        for key, value in fault['details'].iteritems():
            if key in AUDIT_LOG_FIELDS:
                if (key not in audit_log_params and
                        isinstance(value, AUDIT_LOG_FIELDS[key])):
                    audit_log_params[key] = value
                delete.append(key)

        for key in delete:
            del fault['details'][key]

    return audit_log_params


def ErrorFormattingWrapper(observer):
    """
    Return log observer that will format error if any and delegate it to
    given `observer`.

    If the event contains error, the formatter forms a decent message from
    "failure" and "why" and replaces that as message if the event does not
    already contain one. It also adds traceback and exception_type and removes
    existing error fields: "isError", "why" and "failure". "level" is also
    updated if not already found.
    """

    def error_formatting_observer(event):

        message = ""

        if event.get("isError", False):
            level = 3

            if 'failure' in event:
                excp = event['failure'].value
                message = repr(excp)
                event['traceback'] = event['failure'].getTraceback()
                event['exception_type'] = excp.__class__.__name__

            if 'why' in event and event['why']:
                message = '{0}: {1}'.format(event['why'], message)

        else:
            level = 6

        event.update({
            "message": (''.join(event.get("message", '')) or message, ),
            "level": event.get("level", level)
        })
        [event.pop(k, None) for k in ERROR_FIELDS]

        observer(event)

    return error_formatting_observer


def ObserverWrapper(observer, hostname, seconds=None):
    """
    Create a log observer that will format messages and delegate to
    `observer`.

    :param str hostname: The hostname to be used.
    :param ILogObserver observer: The log observer to call with our
        formatted data.
    :param seconds: A 0-argument callable that returns a datetime.

    :rtype: :class:`ILogObserver`
    """

    if seconds is None:  # pragma: no cover
        seconds = time.time

    def Observer(eventDict):

        log_params = {
            "@version": 1,
            "host": hostname,
            "@timestamp": datetime.fromtimestamp(
                eventDict.get("time", seconds())).isoformat(),
            "otter_facility": eventDict.get("system", "otter"),
            "message": eventDict["message"]
        }

        for key, value in eventDict.iteritems():
            if key not in PRIMITIVE_FIELDS:
                log_params[key] = value

        # emit an audit log entry also, if it's an audit log
        if 'audit_log' in eventDict:
            log_params['audit_log_event_source'] = True
            observer(audit_log_formatter(eventDict, log_params['@timestamp'],
                                         hostname))

        observer(log_params)

    return Observer


class ThrottlingWrapper(object):
    """
    An observer that throttles specific messages so they don't spam the logs.
    """

    throttled_messages = [
        pmap({'system': 'kazoo', 'message': ('Received Ping',)}),
        pmap({'system': 'kazoo',
              'message': ('Sending request(xid=-2): Ping()',)}),
        pmap({
            'system': 'otter.silverberg',
            'message': ('CQL query executed successfully',),
            'query': (
                'SELECT "tenantId", "groupId", "policyId", "trigger", '
                'cron, version FROM scaling_schedule_v2 '
                'WHERE bucket = :bucket AND trigger <= :now LIMIT :size;')}),
    ]
    throttle_count = 50

    def __init__(self, observer):
        self.event_counts = {
            template: 0 for template in self.throttled_messages}
        self.observer = observer

    def _get_matching_template(self, event):
        for template in self.throttled_messages:
            if self._match(event, template):
                return template

    def _match(self, event, template):
        """See if a log event matches a throttled message template."""
        for k, v in template.items():
            if (k not in event) or (event[k] != template[k]):
                return False
        return True

    def __call__(self, event):
        """
        If a message matches a throttled template, throttle it, otherwise pass
        it on to the next observer.
        """
        template = self._get_matching_template(event)
        if template is not None:
            self.event_counts[template] += 1
            if self.event_counts[template] >= self.throttle_count:
                event['num_duplicate_throttled'] = (
                    self.event_counts[template])
                self.event_counts[template] = 0
                return self.observer(event)
        else:
            return self.observer(event)
