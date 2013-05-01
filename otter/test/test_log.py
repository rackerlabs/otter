"""
Tests for logging integration.
"""

import json
import mock

from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from otter.log.bound import BoundLog

from otter.log.formatters import JSONObserverWrapper
from otter.log.formatters import StreamObserverWrapper
from otter.log.formatters import GELFObserverWrapper
from otter.log.formatters import SystemFilterWrapper

from otter.test.utils import SameJSON


class BoundLogTests(TestCase):
    """
    Test the BoundLog utility.
    """
    def setUp(self):
        """
        Set up the mocks and a new BoundLog.
        """
        self.msg = mock.Mock()
        self.err = mock.Mock()
        self.log = BoundLog(self.msg, self.err)

    def test_bind_msg(self):
        """
        bind saves it's keyword arguments and passes them to msg when it is called.
        """
        log = self.log.bind(system='hello')
        log.msg('Hi there')

        self.msg.assert_called_once_with('Hi there', system='hello')

    def test_bind_err(self):
        """
        bind saves it's keyword arguments and passes them to err when it is called.
        """
        exc = ValueError('uh oh')
        log = self.log.bind(system='hello')
        log.err(exc)

        self.err.assert_called_once_with(exc, system='hello')


class JSONObserverWrapperTests(TestCase):
    """
    Test the JSON observer wrapper.
    """
    def setUp(self):
        """
        Set up a mock observer.
        """
        self.observer = mock.Mock()

    def test_default_formatter(self):
        """
        JSONObserverWrapper returns an ILogObserver that serializes the eventDict as JSON,
        and calls the wrapped observer with the JSON bytes as the message.
        """
        eventDict = {'foo': 'bar', 'baz': 'bax'}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)
        self.observer.assert_called_once_with({'message': (SameJSON(eventDict),)})

    def test_propagates_keyword_arguments(self):
        """
        JSONObserverWrapper passes keyword arguments to json.dumps.
        """
        eventDict = {'foo': 'bar', 'baz': 'bax'}
        observer = JSONObserverWrapper(self.observer, sort_keys=True)
        observer(eventDict)
        self.observer.assert_called_once_with(
            {'message': (json.dumps(eventDict, sort_keys=True),)})

    def test_repr_fallback(self):
        """
        JSONObserverWrapper serializes non-JSON serializable objects as their
        repr() string.
        """
        class NotSerializable(object):
            def __repr__(self):
                return "NotSerializableRepr"

        eventDict = {'foo': NotSerializable()}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)

        self.observer.assert_called_once_with(
            {'message': (SameJSON({'foo': 'NotSerializableRepr'}),)})


class StreamObserverWrapperTests(TestCase):
    """
    Test the StreamObserverWrapper.
    """
    def setUp(self):
        """
        Set up a mock stream.
        """
        self.stream = mock.Mock()

    def test_unbuffered_output(self):
        """
        StreamObserverWrapper returns an observer that writes to the stream,
        calling flush after every write.
        """
        observer = StreamObserverWrapper(self.stream, buffered=False)
        observer({'message': ('foo',)})
        self.stream.write.assert_has_calls(
            [mock.call('foo'),
             mock.call('\n')])

        self.stream.flush.assert_called_once_with()

    def test_buffered_output(self):
        """
        StreamObserverWrapper returns an observer that writes to the stream,
        calling flush after every write.
        """
        observer = StreamObserverWrapper(self.stream, buffered=True)
        observer({'message': ('foo',)})
        self.stream.write.assert_has_calls(
            [mock.call('foo'),
             mock.call('\n')])

        self.assertEqual(self.stream.flush.call_count, 0)

    def test_non_default_delimiter(self):
        """
        StremaObserverWrapper uses the delimiter specified with the delimiter
        keyword argument.
        """
        observer = StreamObserverWrapper(self.stream, delimiter='\r\n')
        observer({'message': ('foo',)})
        self.stream.write.assert_has_calls(
            [mock.call('foo'),
             mock.call('\r\n')])

    def test_no_delimiter(self):
        """
        StreamObserverWrapper will not write the delimiter if it is None.
        """
        observer = StreamObserverWrapper(self.stream, delimiter=None)
        observer({'message': ('foo',)})
        observer({'message': ('bar',)})
        self.stream.write.assert_has_calls(
            [mock.call('foo'),
             mock.call('bar')])


class _Subdict(object):
    """
    An object that compares equal to a dictionary if all keys in expected_items
    exist in that dictionary and their values compare equal.
    """
    def __init__(self, expected_items):
        self._expected_items = expected_items

    def __eq__(self, other):
        for key, value in self._expected_items.iteritems():
            if key not in other or value != other[key]:
                return False

        return True

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return '{0}({1!r})'.format(self.__class__.__name__, self._expected_items)


class _Contains(object):
    """
    An object that compares equal to another object if it contains `expected_in`.
    """
    def __init__(self, expected_in):
        self._expected_in = expected_in

    def __eq__(self, other):
        return self._expected_in in other

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return '{0}({1!r})'.format(self.__class__.__name__, self._expected_in)


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

    def test_formats_eventDict_a_gelf(self):
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
            _Subdict({'full_message': _Contains('Traceback')}))

    def test_failure_repr_in_short_message(self):
        """
        The observer includes the repr of failure.value in short_message.
        """
        self.gelf({'failure': Failure(ValueError()), 'isError': True})
        self.observer.assert_called_once_with(
            _Subdict({'short_message': repr(ValueError())}))

    def test_isError_with_message_instead_of_failure(self):
        """
        The observer should use message when there is no failure.
        """
        self.gelf({'message': ('uh oh',), 'isError': True})

        self.observer.assert_called_once_with(
            _Subdict({'short_message': 'uh oh',
                      'full_message': 'uh oh'}))

    def test_isError_sets_level_3(self):
        """
        The observer sets the level to 3 (syslog ERROR) when isError is true.
        """

        self.gelf({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            _Subdict({'level': 3}))

    def test_isError_includes_why_in_short_message(self):
        """
        The observer includes 'why' in the short_message when isError is true.
        """
        self.gelf({'failure': Failure(ValueError()),
                   'isError': True,
                   'why': 'Everything is terrible.'})

        self.observer.assert_called_once_with(
            _Subdict({'short_message': _Contains('Everything is terrible.')}))

    def test_includes_structured_data(self):
        """
        The observer includes arbitrary structured data prefixed with an _.
        """
        self.gelf({'uri': 'http://example.com', 'message': 'hooray'})

        self.observer.assert_called_once_with(
            _Subdict({'_uri': 'http://example.com'}))

    def test_includes_file(self):
        """
        The observer includes file if it is specified.
        """
        self.gelf({'message': 'hello', 'file': 'test.py'})

        self.observer.assert_called_once_with(
            _Subdict({'file': 'test.py'}))

    def test_includes_line(self):
        """
        The observer includes line if it is specified.
        """
        self.gelf({'line': 10, 'message': ''})

        self.observer.assert_called_once_with(
            _Subdict({'line': 10}))


class SystemFilterWrapperTests(TestCase):
    """
    Test the SystemFilterWrapper
    """
    def setUp(self):
        """
        Set up a mock observer.
        """
        self.observer = mock.Mock()
        self.sfo = SystemFilterWrapper(self.observer)

    def test_default_system(self):
        """
        SystemFilterObserver rewrites the default twisted system of '-' to
        'otter'.
        """
        self.sfo({'system': '-'})
        self.observer.assert_called_once_with({'system': 'otter'})

    def test_comma_system(self):
        """
        SystemFilterObserver rewrites systems that contain a comma to 'otter',
        storing the original system in 'log_context'.
        """
        self.sfo({'system': 'HTTPChannel,1,127.0.0.1'})
        self.observer.assert_called_once_with({
            'system': 'otter', 'log_context': 'HTTPChannel,1,127.0.0.1'})

    def test_passthrough_system(self):
        """
        SystemFilterObserver passes through all other systems.
        """
        self.sfo({'system': 'otter.rest.blah.blargh'})
        self.observer.assert_called_once_with({'system': 'otter.rest.blah.blargh'})



