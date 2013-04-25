"""
Composable log observers for use with Twisted's log module.
"""
import json
import socket
import time


IGNORE_FIELDS = set(["message", "time", "isError", "system", "id", "failure", "why"])


def GELFObserverWrapper(observer):
    """
    Create a log observer that will format messages as GELF and delegate to
    `observer`.

    :param ILogObserver observer: The log observer to call with our GELF
        formatted data.
    :rtype: ILogObserver
    """
    hostname = socket.gethostname()

    def GELFObserver(eventDict):
        if eventDict["isError"] and 'failure' in eventDict:
            level = 3
            shortMessage = '{0}: {1}'.format(eventDict['why'],
                                             str(eventDict['failure'].value))
            fullMessage = eventDict['failure'].getTraceback()
        else:
            level = 6
            shortMessage = eventDict["message"][0] if eventDict["message"] else ""
            fullMessage = " ".join([str(m) for m in eventDict["message"]])

        log_params = {
            "version": "1.0",
            "host": hostname,
            "short_message": shortMessage,
            "full_message": fullMessage,
            "timestamp": eventDict.get("time", time.time()),
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
