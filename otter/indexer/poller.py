"""
Service that polls a particular AtomHopper feed
"""

import time
from itertools import chain

from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.internet.task import coiterate

from twisted.application.service import Service
from twisted.application.internet import TimerService

from twisted.python import log

from twisted.web.http_headers import Headers

from yunomi import timer

from iso8601 import parse_date

from otter.indexer.atom import parse, entries, previous_link, updated
from otter.indexer.state import DummyStateStore

DEFAULT_INTERVAL = 10


class _BodyReceiver(Protocol):
    def __init__(self):
        self.finish = Deferred()
        self._buffer = []

    def dataReceived(self, data):
        """
        Store data in buffer
        """
        self._buffer.append(data)

    def connectionLost(self, reason):
        """
        Callback the ``finish`` ``Deferred`` with all the data that has
        been written to the buffer.
        """
        self.finish.callback(''.join(self._buffer))


class FeedPollerService(Service):
    """
    Polls AtomHopper feeds
    """
    def __init__(self, agent, url, event_listeners, interval=DEFAULT_INTERVAL,
                 state_store=None,
                 TimerService=TimerService, coiterate=coiterate):
        """
        :param agent: a :class:`twisted.web.client.Agent` to use to poll

        :param url: the url to poll

        :param event_listeners: listeners that handle a particular event
        :type event_listeners: `iterable` of `callables` that take an event
            as an argument

        :param interval: how often to poll, given in seconds - defaults to 10
        :type interval: ``int`` or ``float``

        :param state_store: where to store the current polling state
        :type state_store: :class:`otter.indexer.state.IStateStore` provider

        :param TimerService: factory (not instance) that produces something
            like a :class:`twisted.application.internet.TimerService` -
            defaults to :class:`twisted.application.internet.TimerService`
            (this parameter is mainly used for dependency injection for
            testing)
        :type TimerService: ``callable``

        :param coiterate: function that is used to coiterate tasks - defaults
            to :func:`twisted.internet.task.coiterate` - (this parameter is
            mainly used for dependency injection for testing)
        :type coiterate: ``callable``
        """
        self._url = url
        self._interval = interval

        self._timer_service = TimerService(interval, self._do_poll)

        self._next_url = None

        self._agent = agent
        self._state_store = state_store or DummyStateStore()

        self._event_listeners = event_listeners
        self._poll_timer = timer('FeedPollerService.poll.{0}'.format(url))
        self._fetch_timer = timer('FeedPollerService.fetch.{0}'.format(url))

        self._coiterate = coiterate

    def startService(self):
        """
        Start the feed polling service - called by the twisted
        application when starting up
        """
        self._timer_service.startService()

    def stopService(self):
        """
        Stop the feed polling service - called by the twisted
        application when shutting down

        :return: ``Deferred``
        """
        return self._timer_service.stopService()

    def _fetch(self, url):
        """
        Get atom feed from AtomHopper url
        """
        def _parse(data):
            e = parse(data)
            return e

        def _gotResponse(resp):
            br = _BodyReceiver()

            resp.deliverBody(br)

            return br.finish

        log.msg(format="Fetching url: %(url)r", url=url)
        d = self._agent.request('GET', url, Headers({}), None)
        d.addCallback(_gotResponse)
        d.addCallback(_parse)

        return d

    def _do_poll(self):
        """
        Do one interation of polling AtomHopper.
        """
        start = time.time()

        def _get_next_url(feed):
            self._fetch_timer.update(time.time() - start)
            # next is previous, because AtomHopper is backwards in time
            next_url = previous_link(feed)

            if next_url is not None:
                self._next_url = next_url

            log.msg(format="URLS: %(url)r\n\t->%(next_url)s",
                    url=self._url, next_url=self._next_url)

            sd = self._state_store.save_state(self._next_url)
            sd.addCallback(lambda _: feed)
            return sd

        def _dispatch_entries(feed):
            # Actually sort by updated date.
            sorted_entries = sorted(entries(feed),
                                    key=lambda x: parse_date(updated(x)))
            return self._coiterate(chain.from_iterable(
                                   ((el(entry) for el in self._event_listeners)
                                    for entry in sorted_entries)))

        def _finish_iteration(ignore):
            self._poll_timer.update(time.time() - start)

        d = self._state_store.get_state()
        d.addCallback(
            lambda saved_url: self._next_url or saved_url or self._url)
        d.addCallback(self._fetch)
        d.addCallback(_get_next_url)
        d.addCallback(_dispatch_entries)
        d.addErrback(log.err)
        d.addBoth(_finish_iteration)
        return d
