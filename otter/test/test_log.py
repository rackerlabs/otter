"""
Tests for logging integration.
"""

import json

from StringIO import StringIO

import mock

from twisted.trial.unittest import TestCase

import twiggy
from twiggy import log

from otter.log.formatters import GELFFormat


class TwiggyLoggingTests(TestCase):
    """
    Test the GELFFormat when using the twiggy logging API.
    """
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
        output = twiggy.outputs.StreamOutput(format=GELFFormat('tests'),
                                             stream=self.destination)

        twiggy.addEmitters(('*', twiggy.levels.DEBUG, None, output))

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
        log.fields(foo='bar', baz='bax').info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_foo'], 'bar')
        self.assertEqual(m['_baz'], 'bax')

    def test_fallback(self):
        """
        Non-JSON encodable objects should be serialized as their repr.
        """
        o = object()
        log.fields(foo=o).info('hello')

        m = self.last_logged_json()
        self.assertEqual(m['_foo'], repr(o))
