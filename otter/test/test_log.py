import json

from StringIO import StringIO

import mock

from twisted.trial.unittest import TestCase

import twiggy
from twiggy import log

from otter.log.formatters import JSONFormat


class LoggingTests(TestCase):
    def setUp(self):
        self.destination = StringIO()

        gethostname_patcher = mock.patch('otter.log.formatters.socket.gethostname')
        self.gethostname = gethostname_patcher.start()
        self.addCleanup(gethostname_patcher.stop)
        self.gethostname.return_value = 'my-hostname'

        getpid_patcher = mock.patch('otter.log.formatters.os.getpid')
        self.getpid = getpid_patcher.start()
        self.addCleanup(getpid_patcher.stop)
        self.getpid.return_value = 1000

        _emitters = twiggy.emitters

        def _restore_emitters():
            twiggy.emitters = _emitters

        self.addCleanup(_restore_emitters)

        output = twiggy.outputs.StreamOutput(format=JSONFormat('tests'),
                                             stream=self.destination)

        twiggy.addEmitters(('*', twiggy.levels.DEBUG, None, output))

    def logged_json(self):
        return json.loads(self.destination.getvalue().strip())

    def test_log_includes_separator(self):
        log.info('hello')

        self.assertEqual(self.destination.getvalue()[-1], '\n')

    def test_stripped_log_is(self):
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
