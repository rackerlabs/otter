"""
Tests for logging integration.
"""

import json
import mock
from datetime import datetime

from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

from testtools.matchers import Contains, ContainsDict, Equals

from otter.log.bound import BoundLog

from otter.log.formatters import ObserverWrapper
from otter.log.formatters import JSONObserverWrapper
from otter.log.formatters import PEP3101FormattingWrapper
from otter.log.formatters import StreamObserverWrapper
from otter.log.formatters import SystemFilterWrapper

from otter.test.utils import SameJSON, matches


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
        bind saves it's keyword arguments and passes them to msg when it is
        called.
        """
        log = self.log.bind(system='hello')
        log.msg('Hi there')

        self.msg.assert_called_once_with('Hi there', system='hello')

    def test_bind_err(self):
        """
        bind saves it's keyword arguments and passes them to err when it is
        called.
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
        JSONObserverWrapper returns an ILogObserver that serializes the
        eventDict as JSON, and calls the wrapped observer with the JSON bytes
        as the message.
        """
        eventDict = {'foo': 'bar', 'baz': 'bax'}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)
        self.observer.assert_called_once_with(
            {'message': (SameJSON(eventDict),)})

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

    def test_datetime_logging(self):
        """
        JSONObserverWrapper serializes datetime object in ISO 8601 format
        """
        time = datetime(2012, 10, 20, 5, 36, 23)
        eventDict = {'foo': time}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)
        self.observer.assert_called_once_with(
            {'message': (SameJSON({'foo': '2012-10-20T05:36:23'}),)})

    def test_failure_logging(self):
        """
        JSONObserverWrapper serializes datetime object in ISO 8601 format
        """
        failure = Failure(ValueError('meh'))
        eventDict = {'foo': failure}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)
        self.observer.assert_called_once_with(
            {'message': (SameJSON({'foo': str(failure)}),)})


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
        self.observer.assert_called_once_with(
            {'system': 'otter.rest.blah.blargh'})


class PEP3101FormattingWrapperTests(TestCase):
    """
    Test the PEP3101 Formatting.
    """
    def setUp(self):
        """
        set up a mock observer.
        """
        self.observer = mock.Mock()
        self.wrapper = PEP3101FormattingWrapper(self.observer)

    def test_why_is_None(self):
        """
        PEP3101FormattingWrapper won't format anything if why is not specified
        to log.err.
        """
        self.wrapper({'why': None, 'key': 'value'})
        self.observer.assert_called_once_with({'why': None, 'key': 'value'})

    def test_format_why(self):
        """
        PEP3101FormattingWrapper formats the why argument to log.err.
        """
        self.wrapper({'why': 'Hello {name}', 'name': 'World'})
        self.observer.assert_called_once_with({'why': 'Hello World',
                                               'name': 'World'})

    def test_format_message(self):
        """
        PEP3101FormattingWrapper formats the message.
        """
        self.wrapper({'message': ('foo {bar}',), 'bar': 'bar'})
        self.observer.assert_called_once_with(
            {'message': ('foo bar',), 'bar': 'bar'})

    def test_format_message_tuple(self):
        """
        PEP3101FormattingWrapper joins the message tuple before formatting.
        """
        self.wrapper({'message': ('foo', 'bar', 'baz', '{bax}'), 'bax': 'bax'})
        self.observer.assert_called_once_with(
            {'message': ('foo bar baz bax',), 'bax': 'bax'})

    def test_formatting_failure(self):
        """
        PEP3101FormattingWrapper should fall back to using the unformatted
        message and include an 'exception_formatting_message' key.
        """
        self.wrapper({'message': ('{u"Hello": "There"}',)})
        self.observer.assert_called_once_with({
            'message': '{u"Hello": "There"}',
            'message_formatting_error': matches(Contains('KeyError'))
        })


class ObserverWrapperTests(TestCase):
    """
    Test the ObserverWrapper.
    """
    def setUp(self):
        """
        Set up a mock observer.
        """
        self.observer = mock.Mock()
        self.seconds = mock.Mock(return_value=0)
        self.wrapper = ObserverWrapper(self.observer,
                                       hostname='localhost',
                                       seconds=self.seconds)

    def test_formats_eventDict(self):
        """
        ObserverWrapper calls the wrapped observer with a dictionary.
        """
        self.wrapper({'message': ('Hello',)})

        self.observer.assert_called_once_with({
            'source_host': 'localhost',
            '@version': '1',
            'short_message': 'Hello',
            'message': 'Hello',
            'type': '',
            '@timestamp': '1969-12-31T16:00:00',
            'level': 6,
        })

    def test_failure_include_traceback_in_full_message(self):
        """
        The observer puts the traceback in the full_message key.
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'message': Contains('Traceback')})))

    def test_failure_repr_in_short_message(self):
        """
        The observer includes the repr of failure.value in short_message.
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'short_message': Equals(repr(ValueError()))}))
        )

    def test_isError_with_message_instead_of_failure(self):
        """
        The observer should use message when there is no failure.
        """
        self.wrapper({'message': ('uh oh',), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'short_message': Equals('uh oh'),
                                  'message': Equals('uh oh')})))

    def test_isError_sets_level_3(self):
        """
        The observer sets the level to 3 (syslog ERROR) when isError is true.
        """

        self.wrapper({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'level': Equals(3)})))

    def test_isError_includes_why_in_short_message(self):
        """
        The observer includes 'why' in the short_message when isError is true.
        """
        self.wrapper({'failure': Failure(ValueError()),
                     'isError': True,
                     'why': 'Everything is terrible.'})

        self.observer.assert_called_once_with(
            matches(
                ContainsDict(
                    {'short_message': Contains('Everything is terrible.')})))

    def test_includes_structured_data(self):
        """
        The observer includes arbitrary structured data.
        """
        self.wrapper({'uri': 'http://example.com', 'message': 'hooray'})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'uri': Equals('http://example.com')})))

    def test_includes_file(self):
        """
        The observer includes file if it is specified.
        """
        self.wrapper({'message': 'hello', 'file': 'test.py'})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'file': Equals('test.py')})))

    def test_includes_line(self):
        """
        The observer includes line if it is specified.
        """
        self.wrapper({'line': 10, 'message': ''})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'line': Equals(10)})))
