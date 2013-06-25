"""
Graylog intergration.
"""

import zlib
from txgraylog2.graylogger import GraylogProtocol, GELF_NEW


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
    :params kwargs: Keyword arguments passed directly to
        :class:`txgraylog2.graylogger.GraylogProtocol`
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
