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
    FanoutObserver,
    JSONObserverWrapper,
    LogLevel,
    ObserverWrapper,
    PEP3101FormattingWrapper,
    StreamObserverWrapper,
    SystemFilterWrapper,
    add_to_fanout,
    get_fanout,
    serialize_to_jsonable,
    set_fanout,
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


class FanoutObserverTests(SynchronousTestCase):
    """Tests for :obj:`FanoutObserver`"""

    def test_fanout_single_observer(self):
        """
        Fanout observer successfully sends all events if it only has a single
        subobserver.
        """
        messages = [{str(i): 'message'} for i in range(3)]
        obs = []
        fanout = FanoutObserver(obs.append)
        for mess in messages:
            fanout(mess.copy())
        self.assertEqual(obs, messages)

    def test_fanout_multiple_observers(self):
        """
        More observers can be added to the Fanout observer, which successfully
        sends all new events to all the sub-observers in its list.
        """
        messages = [{str(i): 'message'} for i in range(3)]
        obs1, obs2 = [], []
        fanout = FanoutObserver(obs1.append)
        fanout(messages[0].copy())
        fanout.add_observer(obs2.append)
        fanout(messages[1].copy())
        fanout(messages[2].copy())
        self.assertEqual(obs1, messages)
        self.assertEqual(obs2, messages[1:])

    def test_subobservers_do_not_affect_each_other(self):
        """
        A subobserver that mutates events will not affect other subobservers.
        """
        obs, obs_mutated = [], []

        def mutate(event):
            event.pop('delete_me', None)
            event['added'] = 'added'
            obs_mutated.append(event)

        fanout = FanoutObserver(obs.append)
        fanout.add_observer(mutate)
        fanout({'only': 'message', 'delete_me': 'go'})

        self.assertEqual(obs, [{'only': 'message', 'delete_me': 'go'}])
        self.assertEqual(obs_mutated, [{'only': 'message', 'added': 'added'}])

    def test_global_fanout(self):
        """
        Setting and getting and adding to the global fanout observer.
        """
        obs1, obs2 = [], []
        self.assertEqual(get_fanout(), None)

        # add_to_fanout when there is no fanout
        add_to_fanout(obs1.append)
        fanout = get_fanout()
        self.assertEqual(fanout.subobservers, [obs1.append])

        # add_to_fanout when there is already a fanout
        add_to_fanout(obs2.append)
        self.assertIs(get_fanout(), fanout)
        self.assertEqual(fanout.subobservers, [obs1.append, obs2.append])

        # set_fanout
        set_fanout(None)
        self.assertEqual(get_fanout(), None)
