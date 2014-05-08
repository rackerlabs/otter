"""
Tests for :mod:`otter.indexer.poller`
"""

import mock

from zope.interface import implements

from twisted.trial.unittest import SynchronousTestCase

from twisted.internet.defer import succeed
from twisted.internet.task import Cooperator
from twisted.web.iweb import IResponse
from twisted.web.client import Agent, ResponseDone
from twisted.web.http_headers import Headers

from twisted.application.internet import TimerService

from otter.indexer.poller import FeedPollerService
from otter.test.utils import fixture


class FakeResponse(object):
    """
    A fake response implements the same interface a real
    :class:`twisted.web.client.Response` implements.
    """
    implements(IResponse)

    version = ('HTTP', 1, 1)

    def __init__(self, code, headers, body):
        self.code = code
        self.phrase = 'N/A'
        self.headers = headers
        self.length = len(body)
        self._body = body

    def deliverBody(self, protocol):
        """Methods that writes the body to the given protocol"""
        protocol.dataReceived(self._body)
        protocol.connectionLost(ResponseDone())


def feed_response(fixture_name):
    """
    Load a fixture into the body of a fake response.

    :return: ``Deferred`` that callbacks with the contents of said fixture
    """
    return succeed(FakeResponse(
        200,
        Headers({}),
        fixture(fixture_name)))


class FeedPollerServiceTests(SynchronousTestCase):
    """
    Tests for :class:`otter.indexer.poller.FeedPollerService`
    """

    def setUp(self):
        """
        Create a FeedPollerService with a mock agent, TimerService,
        and cooperator that do not use the real reactor
        """
        self.handler = mock.Mock()
        self.agent = mock.Mock(Agent)
        self.timer = mock.Mock(TimerService)

        self.cooperator = Cooperator(
            scheduler=lambda x: x(),
            started=True
        )

        self.poller = FeedPollerService(
            self.agent, 'http://example.com/feed',
            [self.handler],
            TimerService=self.timer,
            coiterate=self.cooperator.coiterate
        )

        self.poll = self.timer.mock_calls[0][1][1]

    def test_startService(self):
        """
        ``startService`` calls the TimerService's ``startService``
        """
        self.poller.startService()
        self.timer.return_value.startService.assert_called_once_with()

    def test_stopService(self):
        """
        ``stopService`` calls the TimerService's ``stopService``
        """
        self.poller.stopService()
        self.timer.return_value.stopService.assert_called_once_with()

    def test_poll(self):
        """
        During a polling interval, a request is made to the URL specified
        to the constructor of the FeedPollerService, and the response from the
        server is parsed into atom entries, which are then passed to the
        handler.
        """
        self.agent.request.return_value = feed_response('simple.atom')

        self.poll()

        self.agent.request.assert_called_once_with(
            'GET',
            'http://example.com/feed',
            Headers({}),
            None
        )

        self.handler.assert_called_once_with(mock.ANY)
        entry = self.handler.mock_calls[0][1][0]

        self.assertEqual(
            entry.find('./{http://www.w3.org/2005/Atom}id').text,
            'urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a'
        )
