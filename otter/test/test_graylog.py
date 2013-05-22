"""
Tests for graylog integration.
"""
import mock

from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure
from twisted.internet.interfaces import (
    IUDPTransport,
    IReactorUDP,
    IReactorCore,
    IReactorPluggableResolver
)
from twisted.internet.defer import succeed

from testtools.matchers import IsInstance, ContainsDict, Equals, Contains

from otter.log.graylog import GELFObserverWrapper
from otter.test.utils import iMock, patch, matches
from otter.log.graylog import GraylogUDPPublisher
from otter.log.graylog import _GraylogProtocol


class GELFObserverWrapperTests(TestCase):
    """
    Test the GELFObserverWrapper.
    """
    def setUp(self):
        """
        Set up a mock observer.
        """
        self.observer = mock.Mock()
        self.seconds = mock.Mock(return_value=0)
        self.gelf = GELFObserverWrapper(self.observer,
                                        hostname='localhost',
                                        seconds=self.seconds)

    def test_formats_eventDict_as_gelf(self):
        """
        GELFObserverWrapper calls the wrapped observer with a dictionary
        in the GELF format.
        """
        self.gelf({'message': ('Hello',)})

        self.observer.assert_called_once_with({
            'host': 'localhost',
            'version': '1.0',
            'short_message': 'Hello',
            'full_message': 'Hello',
            'facility': '',
            'timestamp': 0,
            'level': 6,
        })

    def test_failure_include_traceback_in_full_message(self):
        """
        The observer puts the traceback in the full_message key.
        """
        self.gelf({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'full_message': Contains('Traceback')})))

    def test_failure_repr_in_short_message(self):
        """
        The observer includes the repr of failure.value in short_message.
        """
        self.gelf({'failure': Failure(ValueError()), 'isError': True})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'short_message': Equals(repr(ValueError()))})))

    def test_isError_with_message_instead_of_failure(self):
        """
        The observer should use message when there is no failure.
        """
        self.gelf({'message': ('uh oh',), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'short_message': Equals('uh oh'),
                                  'full_message': Equals('uh oh')})))

    def test_isError_sets_level_3(self):
        """
        The observer sets the level to 3 (syslog ERROR) when isError is true.
        """

        self.gelf({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'level': Equals(3)})))

    def test_isError_includes_why_in_short_message(self):
        """
        The observer includes 'why' in the short_message when isError is true.
        """
        self.gelf({'failure': Failure(ValueError()),
                   'isError': True,
                   'why': 'Everything is terrible.'})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'short_message': Contains('Everything is terrible.')})))

    def test_includes_structured_data(self):
        """
        The observer includes arbitrary structured data prefixed with an _.
        """
        self.gelf({'uri': 'http://example.com', 'message': 'hooray'})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'_uri': Equals('http://example.com')})))

    def test_includes_file(self):
        """
        The observer includes file if it is specified.
        """
        self.gelf({'message': 'hello', 'file': 'test.py'})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'file': Equals('test.py')})))

    def test_includes_line(self):
        """
        The observer includes line if it is specified.
        """
        self.gelf({'line': 10, 'message': ''})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'line': Equals(10)})))


class GraylogUDPPublisherTests(TestCase):
    """
    Test the GraylogUDPPublisher.
    """
    def setUp(self):
        """
        Mock reactor and transport."
        """
        self.reactor = iMock(IReactorUDP, IReactorCore, IReactorPluggableResolver)
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
        GraylogUDPPublisher does a listenUDP to hook up the publishing protocol.
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

    @mock.patch('txgraylog2.graylogger.randbytes.secureRandom', return_value='secureBytes')
    def test_observer_writes_chunks(self, secureRandom):
        """
        GraylogUDPPublisher chunks messages that exceed chunk_size.

        This uses a really small chunk_size to make it easy to craft a message
        that exceeds it.
        """
        graylog = GraylogUDPPublisher(reactor=self.reactor, chunkSize=10)
        graylog({'message': ('{"short_message": "foo"}',)})

        self.transport.write.assert_has_calls(
            [mock.call('\x1e\x0fsecureBytes\x00\x04x\x9c\xabV*\xce\xc8/*\x89'),
             mock.call('\x1e\x0fsecureBytes\x01\x04\xcfM-.NLOU\xb2R'),
             mock.call('\x1e\x0fsecureBytes\x02\x04PJ\xcb\xcfW\xaa\x05\x00p\xee'),
             mock.call('\x1e\x0fsecureBytes\x03\x04\x08\x93')],
            any_order=False)
