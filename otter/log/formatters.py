"""
Composable log observers for use with Twisted's log module.
"""
import json
import time

from twisted.python.failure import Failure


class ReprFallbackEncoder(json.JSONEncoder):
    """
    A JSONEncoder that will use the repr(obj) as the default serialization
    for objects that the base JSONEncoder does not know about.

    This will ensure that even log messages that include unserializable objects
    (like from 3rd party libraries) will still have reasonable representations
    in the logged JSON and will actually be logged and not discarded by the
    logging system because of a formatting error.
    """
    def default(self, obj):
        """
        Serialize obj as repr(obj).
        """
        return repr(obj)


def JSONObserverWrapper(observer, **kwargs):
    """
    Create an observer that will format the eventDict as JSON using the
    supplied keyword arguments and delegate to `observer`.

    :param ILogObserver observer: The observer to delegate message delivery to.

    :rtype: ILogObserver
    """
    def JSONObserver(eventDict):
        observer({'message': (json.dumps(eventDict, cls=ReprFallbackEncoder, **kwargs),)})

    return JSONObserver


def StreamObserverWrapper(stream, delimiter='\n', buffered=False):
    """
    Create a log observer that will write bytes to the specified stream.
    :param str or None delimter: A delimiter for each message.
    :param bool buffered: True if output should be buffered, if False we will
        call `flush` on the `stream` after writing every message.

    :rtype: ILogObserver
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

    :rtype: ILogObserver
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

    :rtype: ILogObserver
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


IGNORE_FIELDS = set(["message", "time", "isError", "system", "id", "failure", "why"])


def GELFObserverWrapper(observer, hostname, seconds=None):
    """
    Create a log observer that will format messages as GELF and delegate to
    `observer`.

    :param str hostname: The hostname to be used in the gelf format.
    :param ILogObserver observer: The log observer to call with our GELF
        formatted data.
    :param seconds: A 0-argument callable that returns a UNIX timestamp.

    :rtype: ILogObserver
    """

    if seconds is None:  # pragma: no cover
        seconds = time.time

    def GELFObserver(eventDict):
        short_message = None
        full_message = None

        if eventDict.get("isError", False):
            level = 3

            if 'failure' in eventDict:
                short_message = repr(eventDict['failure'].value)
                full_message = eventDict['failure'].getTraceback()

            if 'why' in eventDict and eventDict['why']:
                short_message = '{0}: {1}'.format(eventDict['why'],
                                                  short_message)

        else:
            level = 6

        if not short_message:
            short_message = eventDict["message"][0] if eventDict["message"] else ""

        if not full_message:
            full_message = " ".join([str(m) for m in eventDict["message"]])

        log_params = {
            "version": "1.0",
            "host": hostname,
            "short_message": short_message,
            "full_message": full_message,
            "timestamp": eventDict.get("time", seconds()),
            "level": eventDict.get("level", level),
            "facility": eventDict.get("system", ""),
        }

        if "file" in eventDict:
            log_params["file"] = eventDict["file"]
        if "line" in eventDict:
            log_params["line"] = eventDict["line"]

        for key, value in eventDict.iteritems():
            if key not in IGNORE_FIELDS:
                log_params["_%s" % (key, )] = value

        observer(log_params)

    return GELFObserver
