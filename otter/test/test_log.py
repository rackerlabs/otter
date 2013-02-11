import json

from StringIO import StringIO

import mock

from twisted.trial.unittest import TestCase

import twiggy
from twiggy import log

from otter.log.formatters import GELFFormat


class LoggingTests(TestCase):
    def setUp(self):
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

    def logged_json(self):
        return json.loads(self.destination.getvalue().split('\n')[-2])

    def test_log_includes_separator(self):
        log.info('hello')

        value_list = self.destination.getvalue().split('\n')
        self.assertEqual(len(value_list), 2)
        self.assertEqual(value_list[-1], '')

    def test_stripped_log_is_json_object(self):
        log.info('hello')

        self.assertIsInstance(self.logged_json(), dict)

    def test_default_facility(self):
        log.info('hello')

        m = self.logged_json()

        self.assertEqual(m['facility'], 'tests')

    def test_named_facility(self):
        log.name('named_test').info('hello')

        m = self.logged_json()
        self.assertEqual(m['facility'], 'named_test')

    def test_hostname(self):
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['host'], 'my-hostname')

    def test_pid(self):
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['_pid'], 1000)

    def test_thread_name(self):
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['_thread_name'], 'my-thread')

    def test_log_level(self):
        levels = [(log.info, 6),
                  (log.error, 3),
                  (log.critical, 2),
                  (log.warning, 4),
                  (log.debug, 7)]

        for m, i in levels:
            m('hello')
            m = self.logged_json()
            self.assertEqual(m['level'], i)

    def test_version(self):
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['version'], '1.0')

    def test_short_message(self):
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['short_message'], 'hello')

    def test_timestmap(self):
        # TODO: Assert something about the value passed to mktime.
        log.info('hello')

        m = self.logged_json()
        self.assertEqual(m['timestamp'], 1)

    def test_traceback_as_full_message(self):
        try:
            1/0
        except:
            log.trace().error('an error happened')

        m = self.logged_json()
        self.assertEqual(m['short_message'], 'an error happened')
        self.assertIn('ZeroDivisionError: integer division or modulo by zero',
                      m['full_message'])

    def test_fields(self):
        log.fields(foo='bar', baz='bax').info('hello')

        m = self.logged_json()
        self.assertEqual(m['_foo'], 'bar')
        self.assertEqual(m['_baz'], 'bax')

    def test_fallback(self):
        o = object()
        log.fields(foo=o).info('hello')

        m = self.logged_json()
        self.assertEqual(m['_foo'], repr(o))

