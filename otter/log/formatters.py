"""
Composable log observers for use with Twisted's log module.
"""
import json
import time
from datetime import datetime

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
        observer({'message': (json.dumps(eventDict, cls=LoggingEncoder, **kwargs),)})

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


IGNORE_FIELDS = set(["message", "time", "isError", "system", "id", "failure",
                     "why", "audit_log"])

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
        message = None

        log_params = {
            "@version": 1,
            "host": hostname,
            "@timestamp": datetime.fromtimestamp(
                eventDict.get("time", seconds())).isoformat(),
            "otter_facility": eventDict.get("system", "otter"),
        }

        if eventDict.get("isError", False):
            level = 3

            if 'failure' in eventDict:
                message = repr(eventDict['failure'].value)
                log_params['traceback'] = eventDict['failure'].getTraceback()

            if 'why' in eventDict and eventDict['why']:
                message = '{0}: {1}'.format(eventDict['why'], message)

        else:
            level = 6

        if not message:
            message = eventDict["message"][0] if eventDict["message"] else ""

        log_params.update({
            "message": message,
            "level": eventDict.get("level", level),
        })

        if "file" in eventDict:
            log_params["file"] = eventDict["file"]
        if "line" in eventDict:
            log_params["line"] = eventDict["line"]

        for key, value in eventDict.iteritems():
            if key not in IGNORE_FIELDS:
                log_params["%s" % (key, )] = value

        # emit an audit log entry also, if it's an audit log
        if 'audit_log' in eventDict:
            log_params['audit_log_event_source'] = True
            observer(audit_log_formatter(eventDict, log_params['@timestamp'],
                                         hostname))

        observer(log_params)

    return Observer
