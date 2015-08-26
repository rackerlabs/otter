"""
Composable log observers for use with Twisted's log module.
"""
import json
import time
from datetime import datetime

from pyrsistent import pmap

from singledispatch import singledispatch

from twisted.python.failure import Failure


THROTTLED_MESSAGES = [
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

THROTTLE_COUNT = 50

NON_PEP3101_SYSTEMS = ('kazoo',)


_fanout = None


def add_to_fanout(observer):
    """
    :return: the global instance of :class:`FanoutObserver`
    """
    global _fanout
    if _fanout is None:
        _fanout = FanoutObserver(observer)
    else:
        _fanout.add_observer(observer)


def get_fanout():
    """
    :return: the global instance of :class:`FanoutObserver`
    """
    return _fanout


def set_fanout(fanout):
    """
    Set the global instance of :class:`FanoutObserver`.
    """
    global _fanout
    _fanout = fanout


class FanoutObserver(object):
    """
    A fanout observer that emits events that it receives to all its sub
    observers.
    """
    def __init__(self, observer):
        """
        Initialize the subobservers with the first observer.
        """
        self.subobservers = [observer]

    def add_observer(self, observer):
        """
        Add another observer to the subobservers.
        """
        self.subobservers.append(observer)

    def __call__(self, event_dict):
        """
        Emit a copy of the event dict to every subobserver.
        """
        for ob in self.subobservers:
            ob(event_dict.copy())


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
        if (eventDict.get('why') and
                eventDict.get('system') not in NON_PEP3101_SYSTEMS):
            eventDict['why'] = eventDict['why'].format(**eventDict)

        if 'message' in eventDict:
            message = ' '.join(eventDict['message'])

            if message and eventDict.get('system') not in NON_PEP3101_SYSTEMS:
                try:
                    eventDict['message'] = (message.format(**eventDict),)
                except Exception:
                    failure = Failure()
                    eventDict['message_formatting_error'] = str(failure)
                    eventDict['message'] = message

        observer(eventDict)

    return PEP3101FormattingObserver


ERROR_FIELDS = {"isError", "failure", "why"}

PRIMITIVE_FIELDS = {"time", "system", "id", "audit_log", "message"}


@singledispatch
def serialize_to_jsonable(obj):
    """
    Serialize any object to a JSONable form
    """
    return repr(obj)


class LogLevel(object):
    """ Log levels """
    INFO = 6
    ERROR = 3


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
            level = LogLevel.ERROR

            if 'failure' in event:
                excp = event['failure'].value
                message = repr(excp)
                event['traceback'] = event['failure'].getTraceback()
                event['exception_type'] = excp.__class__.__name__
                details = serialize_to_jsonable(excp)
                if details != message:
                    event['error_details'] = details

            if 'why' in event and event['why']:
                message = '{0}: {1}'.format(event['why'], message)

        else:
            level = LogLevel.INFO

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

        observer(log_params)

    return Observer


def throttling_wrapper(observer):
    """
    An observer that throttles specific messages so they don't spam the logs.
    """
    event_counts = {template: 0 for template in THROTTLED_MESSAGES}
    observer = observer

    def _get_matching_template(event):
        for template in THROTTLED_MESSAGES:
            if _match(event, template):
                return template

    def _match(event, template):
        """See if a log event matches a throttled message template."""
        for k, v in template.items():
            if (k not in event) or (event[k] != template[k]):
                return False
        return True

    def emit(event):
        template = _get_matching_template(event)
        if template is not None:
            event_counts[template] += 1
            if event_counts[template] >= THROTTLE_COUNT:
                event['num_duplicate_throttled'] = (
                    event_counts[template])
                event_counts[template] = 0
                return observer(event)
        else:
            return observer(event)

    return emit
