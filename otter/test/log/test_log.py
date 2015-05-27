"""
Tests for logging integration.
"""

import json
from datetime import datetime

import mock

from testtools.matchers import (
    Contains,
    ContainsDict,
    Equals)

from twisted.python.failure import Failure
from twisted.trial.unittest import SynchronousTestCase

from otter.log import audit
from otter.log.bound import BoundLog
from otter.log.formatters import (
    ErrorFormattingWrapper,
    JSONObserverWrapper,
    LogLevel,
    ObserverWrapper,
    PEP3101FormattingWrapper,
    StreamObserverWrapper,
    SystemFilterWrapper,
    audit_log_formatter,
    serialize_to_jsonable,
    throttling_wrapper)
from otter.test.utils import SameJSON, matches


class BoundLogTests(SynchronousTestCase):
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


class AuditLoggerTests(SynchronousTestCase):
    """
    Test the method that binds the audit log
    """
    def setUp(self):
        """
        Set up the mocks and a new BoundLog.
        """
        self.msg = mock.Mock()
        self.err = mock.Mock()
        self.log = BoundLog(self.msg, self.err)

    def test_audit_msg(self):
        """
        audit_log keyword is bound when msg is called
        """
        auditlog = audit(self.log)
        auditlog.msg('hey')
        self.msg.assert_called_once_with('hey', audit_log=True)

    def test_audit_err(self):
        """
        audit_log keyword is bound when err is called
        """
        exc = ValueError('boo')
        auditlog = audit(self.log)
        auditlog.err(exc)
        self.err.assert_called_once_with(exc, audit_log=True)


class JSONObserverWrapperTests(SynchronousTestCase):
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

    def test_message_is_concatenated(self):
        """
        message tuple in event is concatenated before passing on
        """
        eventDict = {'message': ('mine', 'yours')}
        observer = JSONObserverWrapper(self.observer)
        observer(eventDict)
        self.observer.assert_called_once_with(
            {'message': (SameJSON({'message': 'mineyours'}),)})


class StreamObserverWrapperTests(SynchronousTestCase):
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


class SystemFilterWrapperTests(SynchronousTestCase):
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


class PEP3101FormattingWrapperTests(SynchronousTestCase):
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

    def test_no_format_why_if_system_is_ignored(self):
        """
        PEP3101FormattingWrapper does not format the why argument to log.err
        if the system is an ignored system.
        """
        self.wrapper({'why': 'Hello {name}', 'name': 'World',
                      'system': 'kazoo'})
        self.observer.assert_called_once_with({'why': 'Hello {name}',
                                               'name': 'World',
                                               'system': 'kazoo'})

    def test_format_message(self):
        """
        PEP3101FormattingWrapper formats the message.
        """
        self.wrapper({'message': ('foo {bar}',), 'bar': 'bar'})
        self.observer.assert_called_once_with(
            {'message': ('foo bar',), 'bar': 'bar'})

    def test_no_format_message_if_system_is_ignored(self):
        """
        PEP3101FormattingWrapper does not format the message if the system is
        an ignored system.
        """
        self.wrapper({'message': ('foo {bar}',), 'bar': 'bar',
                      'system': 'kazoo'})
        self.observer.assert_called_once_with(
            {'message': ('foo {bar}',), 'bar': 'bar', 'system': 'kazoo'})

    def test_format_message_tuple(self):
        """
        PEP3101FormattingWrapper joins the message tuple before formatting.
        """
        self.wrapper({'message': ('foo', 'bar', 'baz', '{bax}'), 'bax': 'bax'})
        self.observer.assert_called_once_with(
            {'message': ('foo bar baz bax',), 'bax': 'bax'})

    def test_no_joins_no_format_message_tuple(self):
        """
        PEP3101FormattingWrapper neither joins nor formats the message tuple
        if the system is an ignored system.
        """
        self.wrapper({'message': ('foo', 'bar', 'baz', '{bax}'),
                      'bax': 'bax',
                      'system': 'kazoo'})
        self.observer.assert_called_once_with(
            {'message': ('foo', 'bar', 'baz', '{bax}',), 'bax': 'bax',
             'system': 'kazoo'})

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


class ErrorFormatterTests(SynchronousTestCase):
    """
    Test for ErrorFormatterTests
    """

    def setUp(self):
        """
        Set up a mock observer.
        """
        self.observer = mock.Mock()
        self.wrapper = ErrorFormattingWrapper(self.observer)

    def _formatted_event(self):
        args, _ = self.observer.call_args
        return args[0]

    def test_no_failure(self):
        """
        If event does not have failure, it sets level to LogLevel.INFO
        and removes all error fields
        """
        self.wrapper({'isError': False, 'failure': 'f', 'why': 'w',
                      'foo': 'bar'})
        self.assertEqual(
            self._formatted_event(),
            {'level': LogLevel.INFO, 'message': ('',), 'foo': 'bar'})

    def test_failure_include_traceback_in_event_dict(self):
        """
        The observer puts the traceback in the ``traceback`` key.
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'traceback': Contains('Traceback')})))

    def test_failure_repr_in_short_message(self):
        """
        The observer includes the repr of failure.value in short_message.
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'message': Equals((repr(ValueError()),))})))

    def test_isError_with_message_instead_of_failure(self):
        """
        The observer should use message when there is no failure.
        """
        self.wrapper({'message': ('uh oh',), 'isError': True})

        self.observer.assert_called_once_with(
            matches(ContainsDict({'message': Equals(('uh oh',))})))

    def test_isError_sets_level_error(self):
        """
        The observer sets the level to LogLevel.ERROR when isError is true.
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'level': Equals(LogLevel.ERROR)})))

    def test_isError_removes_error_fields(self):
        """
        Observer removes error fields before delegating when there
        is failure in event
        """
        self.wrapper({'failure': Failure(ValueError()), 'isError': True,
                      'why': 'reason'})
        event = self._formatted_event()
        for e in ('failure', 'why', 'isError'):
            self.assertNotIn(e, event)

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
                    {'message': Equals(
                        ('Everything is terrible.: ValueError()',))})))

    def test_contains_exception_type(self):
        """
        The observer includes "exception_type" if event contains error
        """
        self.wrapper({'failure': Failure(ValueError()),
                      'isError': True})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'exception_type': Equals("ValueError")})))

    def test_empty_message(self):
        """
        Empty message in event is overwritten with failure message
        """
        self.wrapper({'message': (), 'isError': True,
                      'failure': Failure(ValueError())})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'message': Equals(('ValueError()',))})))

    def test_message_why_iserror(self):
        """
        When message, why and isError is given, then message takes precedence
        and why and isError is ignored to construct message
        """
        failure = Failure(ValueError())
        self.wrapper({'message': ('mine', 'yours'), 'isError': True,
                      'why': 'reason', 'failure': failure})
        self.assertEqual(
            self._formatted_event(),
            {'message': ('mineyours',), 'level': LogLevel.ERROR,
             'traceback': failure.getTraceback(),
             'exception_type': 'ValueError'})

    def test_details(self):
        """
        If exception is serializable, then it is serialized and logged as
        "error_details"
        """
        class MyException(Exception):
            pass

        @serialize_to_jsonable.register(MyException)
        def _(excp):
            return 'mine'

        err = MyException('heh')
        self.wrapper({'message': (), 'isError': True, 'failure': Failure(err)})
        self.observer.assert_called_once_with(
            matches(ContainsDict({'error_details': Equals('mine')})))


class ObserverWrapperTests(SynchronousTestCase):
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
            'host': 'localhost',
            '@version': 1,
            'message': ('Hello',),
            'otter_facility': 'otter',
            '@timestamp': datetime.fromtimestamp(0).isoformat()
        })

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

    def test_generates_new_audit_log(self):
        """
        The observer generates two logs for an audit-loggable eventDict -
        the audit log dictionary and a regular log (passes timestamp and
        hostname too)
        """
        self.wrapper({'message': 'meh', 'audit_log': True, 'time': 1234.0})
        self.observer.has_calls([
            mock.call(matches(ContainsDict({'message': Equals('meh'),
                                            'audit_log': Equals(True),
                                            '@timestamp': Equals(1234),
                                            'host': Equals('hostname')}))),
            mock.call(matches(ContainsDict({
                'short_message': Equals('meh'),
                'audit_log_event_source': Equals(True)})))
        ])


class AuditLogFormatterTests(SynchronousTestCase):
    """
    Tests the audit log formatter
    """
    def test_filters_out_extraneous_fields(self):
        """
        audit log formatter filters extraneous fields out of the event dict
        """
        self.assertEquals(
            audit_log_formatter({'message': ('Hello',), 'what': 'the'}, 0,
                                'hostname'),
            {
                '@version': 1,
                'message': 'Hello',
                '@timestamp': 0,
                'host': 'hostname',
                'is_error': False
            })

    def test_always_includes_fault_dict_even_if_no_failure(self):
        """
        Even if it doesn't include a failure, if it's an error message a
        fault dictionary will be specified.  is_error will also be True.
        """
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes'}, 0,
                                'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh.',
                '@timestamp': 0,
                'is_error': True,
                'host': 'hostname',
                'fault': {'details': {}}
            })

    def test_error_formats_why_message(self):
        """
        The why message is formatted into the message if it's an error.
        """
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes',
                                 'why': 'is the sky blue'}, 0,
                                'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh. is the sky blue',
                '@timestamp': 0,
                'is_error': True,
                'host': 'hostname',
                'fault': {'details': {}}
            })

    def test_error_formats_Exception_message(self):
        """
        The error message is formatted into the fault dict if it's an error.
        """
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes',
                                 'failure': Failure(ValueError('boo'))}, 0,
                                'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh.',
                '@timestamp': 0,
                'is_error': True,
                'host': 'hostname',
                'fault': {'details': {}, 'message': 'boo'}
            })

    def test_error_keeps_fault_dictionary(self):
        """
        The fault dictionary, if included, is not clobbered by the failure
        """
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes',
                                 'fault': {'details': {'x': 'y'},
                                           'message': '1'},
                                 'failure': Failure(ValueError('boo'))}, 0,
                                'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh.',
                '@timestamp': 0,
                'is_error': True,
                'host': 'hostname',
                'fault': {
                    'message': '1',
                    'details': {'x': 'y'}
                }
            })

    def test_error_updates_fault_details(self):
        """
        The details dictionary, if included, does not get clobbered by the
        errors's details
        """
        exc = ValueError('boo')
        exc.details = {'1': 2, '3': 5}
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes',
                                 'fault': {'details': {'x': 'y'},
                                           'message': '1'},
                                 'failure': Failure(exc)}, 0, 'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh.',
                '@timestamp': 0,
                'is_error': True,
                'host': 'hostname',
                'fault': {
                    'message': '1',
                    'details': {'x': 'y', '1': 2, '3': 5}
                }
            })

    def test_error_pulls_some_fault_details_keys_into_main_log(self):
        """
        If audit log parameters are in the details dictionary,
        they are removed.

        If they are valid values, they are pulled out and put in the
        main audit log, but without clobbering existing values in the
        main audit log.
        """
        exc = ValueError('boo')
        exc.details = {'1': 2, 'scaling_group_id': '5', 'tenant_id': '1',
                       'fault': {}, 'policy_id': False}
        self.assertEquals(
            audit_log_formatter({'message': ('meh',), 'isError': 'yes',
                                 'tenant_id': '5',
                                 'fault': {'details': {'x': 'y'},
                                           'message': '1'},
                                 'failure': Failure(exc)}, 0, 'hostname'),
            {
                '@version': 1,
                'message': 'Failed: meh.',
                '@timestamp': 0,
                'is_error': True,
                'scaling_group_id': '5',
                'tenant_id': '5',
                'host': 'hostname',
                'fault': {
                    'message': '1',
                    'details': {'x': 'y', '1': 2}
                }
            })


class ThrottlingWrapperTests(SynchronousTestCase):
    """Tests for :obj:`ThrottlingWrapper`."""

    def test_non_matching(self):
        """If a log doesn't match a template, it's just logged as normal."""
        logs = []
        observer = logs.append
        throttler = throttling_wrapper(observer)
        event = {'message': ('foo bar',), 'system': 'baz'}
        throttler(event)
        self.assertEqual(logs, [event])

    def test_matching(self):
        """
        If a log matches a template, it's not immediately logged.
        """
        logs = []
        observer = logs.append
        throttler = throttling_wrapper(observer)
        event = {'message': ('Received Ping',), 'system': 'kazoo'}
        throttler(event)
        self.assertEqual(logs, [])

    def test_aggregate(self):
        """
        After so many events are received, a matching message gets logged along
        with the number of times it was throttled.
        """
        logs = []
        observer = logs.append
        throttler = throttling_wrapper(observer)
        event = {'message': ('Received Ping',), 'system': 'kazoo'}
        for i in range(50):
            throttler(event)
        self.assertEqual(
            logs,
            [{'message': ('Received Ping',), 'system': 'kazoo',
              'num_duplicate_throttled': 50}])
