"""
Graylog intergration.
"""

import time
import zlib

from txgraylog2.graylogger import GraylogProtocol, GELF_NEW


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


class _GraylogProtocol(GraylogProtocol):
    """
    A graylog protocol implementation that assumes it's being given,
    GELF formatted JSON as byte strings.
    """
    def generateGELFMessages(self, json_message):
        """
        Handle a generating an iterable of chunks from a gelf formatted
        dictionary as opposed to an eventDict.

        :param str json_message: Encoded JSON assumed to already be GELF.
        :return: iterable of bytestrings that will be written to the graylog
            server.
        """
        compressed = zlib.compress(json_message)

        if len(compressed) > self.chunkSize:
            return self.getChunks(compressed)

        return [compressed]


def GraylogUDPPublisher(host='127.0.0.1', port=12201, reactor=None, **kwargs):
    """
    Publish previously gelf formatted JSON encoded messages to a graylog server
    over UDP.

    :param str host: IP address of the graylog server.
    :param int port: UDP port of the graylog server.
    :params kwargs: Keyword arguments passed directly to txgraylog2.graylogger.GraylogProtocol
    :param IReactorUDP,IReactorTime,None reactor: An instance of a reactor or None

    :rtype: ILogObserver
    """
    if reactor is None:  # pragma: no cover
        from twisted.internet import reactor

    protocol = _GraylogProtocol(host, port, gelfFormat=GELF_NEW, **kwargs)
    reactor.listenUDP(0, protocol)

    def GraylogUDPPublishingObserver(eventDict):
        protocol.logMessage(''.join(eventDict['message']))

    return GraylogUDPPublishingObserver
