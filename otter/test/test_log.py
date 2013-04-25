"""
Tests for logging integration.
"""

import json

from StringIO import StringIO

import mock

from twisted.trial.unittest import TestCase
from twisted.python import log as tplog
from twisted.python.failure import Failure

from otter.log.bound import BoundLog
from otter.log import log as olog

from otter.log.formatters import JSONObserverWrapper
from otter.log.formatters import StreamObserverWrapper
from otter.test.utils import SameJSON

#from otter.log.formatters import GELFFormat


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


class TwiggyLoggingTests(TestCase):
    """
    Test the GELFFormat when using the twiggy logging API.
    """
    skip = "Oh well.."

    def setUp(self):
        """
        Set up test dependencies.
        """
        self.destination = StringIO()

        # Patch gethostname so we get a consistent hostname.
        gethostname_patcher = mock.patch('otter.log.formatters.socket.gethostname')
        self.gethostname = gethostname_patcher.start()
        self.addCleanup(gethostname_patcher.stop)
        self.gethostname.return_value = 'my-hostname'

        # Patch getpid so we get a consistent pid.
        getpid_patcher = mock.patch('otter.log.formatters.os.getpid')
        self.getpid = getpid_patcher.start()
        self.addCleanup(getpid_patcher.stop)
        self.getpid.return_value = 1000

        # Patch thread_name so we get a consistent thread name.
        thread_name_patcher = mock.patch('otter.log.formatters.thread_name')
        self.thread_name = thread_name_patcher.start()
        self.addCleanup(thread_name_patcher.stop)
        self.thread_name.return_value = 'my-thread'

        mktime_patcher = mock.patch('otter.log.formatters.time.mktime')
        self.mktime = mktime_patcher.start()
        self.addCleanup(mktime_patcher.stop)
        self.mktime.return_value = 1

        # Save twiggy emitters so we can restore them after tests.
        _emitters = twiggy.emitters

        def _restore_emitters():
            twiggy.emitters = _emitters

        self.addCleanup(_restore_emitters)

        # Configure output just for tests.
        # output = twiggy.outputs.StreamOutput(format=GELFFormat('tests'),
        #                                      stream=self.destination)

        # twiggy.addEmitters(('*', twiggy.levels.DEBUG, None, output))

        observer = TwiggyLoggingObserver()
        _observers = tplog.theLogPublisher.observers
        tplog.theLogPublisher.observers = []
        tplog.addObserver(observer.emit)

        def _restore_observers():
            tplog.theLogPublisher.observers = _observers

        self.addCleanup(_restore_observers)

    def last_logged_json(self):
        """
        Return the last log line parsed as JSON.
        """
        return json.loads(self.destination.getvalue().split('\n')[-2])

    def test_log_includes_separator(self):
        """
        Formatted log lines should include the configured separator as a suffix.
        """
        log.info('hello')

        value_list = self.destination.getvalue().split('\n')
        self.assertEqual(len(value_list), 2)
        self.assertEqual(value_list[-1], '')

    def test_stripped_log_is_json_object(self):
        """
        Formatted log lines should be parseable as JSON, and be JSON objects.
        """
        log.info('hello')

        self.assertIsInstance(self.last_logged_json(), dict)

    def test_default_facility(self):
        """
        Formatted log lines should include the default facility configured in
        GELFFormat.
        """
        log.info('hello')

        m = self.last_logged_json()

        self.assertEqual(m['facility'], 'tests')

    def test_named_facility(self):
        """
        Formatted log lines should use the name of a bound logger as the facility,
        if available.
        """
        log.name('named_test').info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['facility'], 'named_test')

    def test_hostname(self):
        """
        Formatted log lines should include the hostname from socket.gethostname.
        """
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['host'], 'my-hostname')

    def test_pid(self):
        """
        Formatted log lines should include the pid from os.getpid()
        """
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_pid'], 1000)

    def test_thread_name(self):
        """
        Formatted log lines should include the name of the current thread.
        """
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_thread_name'], 'my-thread')

    def test_log_level(self):
        """
        Formatted log lines should include a syslog level converted from
        twiggy log levels.
        """
        levels = [(log.info, 6),
                  (log.error, 3),
                  (log.critical, 2),
                  (log.warning, 4),
                  (log.debug, 7)]

        for m, i in levels:
            m('hello')
            m = self.last_logged_json()
            self.assertEqual(m['level'], i)

    def test_version(self):
        """
        Formatted log lines should include the GELF format version.
        """
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['version'], '1.0')

    def test_short_message(self):
        """
        The argument passed to the twiggy log method should be used as the
        short_message.
        """
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'hello')

    def test_timestmap(self):
        """
        The timestamp in the formatted log message should be a unix timestamp.
        """
        # TODO: Assert something about the value passed to mktime.
        log.info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['timestamp'], 1)

    def test_traceback_as_full_message(self):
        """
        The traceback should be included as a string in full_message.
        """
        try:
            1 / 0
        except:
            log.trace().error('an error happened')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'an error happened')
        self.assertIn('ZeroDivisionError: integer division or modulo by zero',
                      m['full_message'])

    def test_fields(self):
        """
        Log fields should be included in the formatted message prefixed with
        an underscore.
        """
        log.fields(foo='bar', baz='bax {').info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_foo'], 'bar')
        self.assertEqual(m['_baz'], 'bax {')

    def test_fallback(self):
        """
        Non-JSON encodable objects should be serialized as their repr.
        """
        o = object()
        log.fields(foo=o).info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_foo'], repr(o))

    def test_twisted_log_msg(self):
        """
        Log messages from twisted's logging API should be correctly formatted.
        """
        tplog.msg('hello')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'hello')

    def test_twisted_log_err_with_reason(self):
        """
        Errors logged with an explicit reason should be correctly formatted.
        """
        try:
            1 / 0
        except:
            tplog.err(_why='an error occurred')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'an error occurred')
        self.assertIn('ZeroDivisionError: integer division or modulo by zero',
                      m['full_message'])

    def test_twisted_log_err_without_reason(self):
        """
        Errors logged without a reason should be logged as Unhandled Error.
        """
        try:
            1 / 0
        except:
            tplog.err()

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'Unhandled Error')
        self.assertIn('ZeroDivisionError: integer division or modulo by zero',
                      m['full_message'])

    def test_base_logger(self):
        """
        The base logger is bound to the 'otter' name.
        """
        olog.info('foo')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'foo')
        self.assertEqual(m['facility'], 'otter')

    def test_base_logger_failure_feature(self):
        """
        The base logger supports the failure feature.
        """

        try:
            1 / 0
        except:
            olog.failure(Failure()).error('uh oh')

        m = self.last_logged_json()
        self.assertEqual(m['short_message'], 'uh oh')
        self.assertIn('ZeroDivisionError: integer division or modulo by zero',
                      m['full_message'])
