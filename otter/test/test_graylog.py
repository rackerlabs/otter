"""
Tests for graylog integration.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.internet.interfaces import (
    IUDPTransport,
    IReactorUDP,
    IReactorCore,
    IReactorPluggableResolver
)
from twisted.internet.defer import succeed

from testtools.matchers import IsInstance

from otter.test.utils import iMock, patch, matches
from otter.log.graylog import GraylogUDPPublisher
from otter.log.graylog import _GraylogProtocol


class GraylogUDPPublisherTests(TestCase):
    """
    Test the GraylogUDPPublisher.
    """
    def setUp(self):
        """
        Mock reactor and transport."
        """
        self.reactor = iMock(IReactorUDP, IReactorCore,
                             IReactorPluggableResolver)
        patch(self, 'txgraylog2.graylogger.reactor', new=self.reactor)
        self.transport = iMock(IUDPTransport)

        def listenUDP(port, proto):
            proto.makeConnection(self.transport)

        self.reactor.listenUDP.side_effect = listenUDP

        def callWhenRunning(f, *args, **kwargs):
            f(*args, **kwargs)

        self.reactor.callWhenRunning = callWhenRunning

        self.reactor.resolve.return_value = succeed('127.0.0.1')

        self.graylog = GraylogUDPPublisher(reactor=self.reactor)

    def test_wrapper_listens(self):
        """
        GraylogUDPPublisher does a listenUDP to hook up the
        publishing protocol.
        """
        self.reactor.listenUDP.assert_called_once_with(
            0,
            matches(IsInstance(_GraylogProtocol)))

    def test_observer_extracts_message(self):
        """
        GraylogUDPPublisher extracts the message tuple from the eventDict and
        writes it to our protocol.
        """
        self.graylog({'message': ('{"short_message": "foo"}',)})
        self.transport.write.assert_called_once_with(
            'x\x9c\xabV*\xce\xc8/*\x89\xcfM-.NLOU\xb2RPJ\xcb\xcfW\xaa\x05\x00p\xee\x08\x93')

    @mock.patch('txgraylog2.graylogger.randbytes.secureRandom',
                return_value='secureBytes')
    def test_observer_writes_chunks(self, secureRandom):
        """
        GraylogUDPPublisher chunks messages that exceed chunk_size.

        This uses a really small chunk_size to make it easy to craft a message
        that exceeds it.
        """
        graylog = GraylogUDPPublisher(reactor=self.reactor, chunkSize=10)
        graylog({'message': ('{"short_message": "foo"}',)})

        self.transport.write.assert_has_calls(
            [mock.call(
                '\x1e\x0fsecureBytes\x00\x04x\x9c\xabV*\xce\xc8/*\x89'),
             mock.call('\x1e\x0fsecureBytes\x01\x04\xcfM-.NLOU\xb2R'),
             mock.call(
                 '\x1e\x0fsecureBytes\x02\x04PJ\xcb\xcfW\xaa\x05\x00p\xee'),
             mock.call('\x1e\x0fsecureBytes\x03\x04\x08\x93')],
            any_order=False)
