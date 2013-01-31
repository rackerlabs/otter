"""
Tests for the otter-api tap plugin.
"""

import mock

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.tap.api import Options, makeService


class APIOptionsTests(TestCase):
    """
    Test the various command line options.
    """
    def test_options(self):
        """
        The port long option should end up in the 'port' key.
        """
        config = Options()
        config.parseOptions(['--port=tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')

    def test_short_options(self):
        """
        The p short option should end up in the 'port' key.
        """
        config = Options()
        config.parseOptions(['-p', 'tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')


class APIMakeServiceTests(TestCase):
    """
    Test creation of the API service heirarchy.
    """
    def setUp(self):
        """
        Configure mocks for Site and the strports service constructor.
        """
        service_patcher = mock.patch('otter.tap.api.service')
        self.service = service_patcher.start()
        self.addCleanup(service_patcher.stop)

        site_patcher = mock.patch('otter.tap.api.Site')
        self.Site = site_patcher.start()
        self.addCleanup(site_patcher.stop)

    def test_service_site_on_port(self):
        """
        makeService will create a strports service on tcp:9999 with a
        Site instance.
        """
        makeService({'port': 'tcp:9999'})
        self.service.assert_called_with('tcp:9999', self.Site.return_value)

    def test_is_MultiService(self):
        """
        makeService will return a MultiService.
        """
        self.assertIsInstance(makeService({'port': 'tcp:9999'}), MultiService)

    def test_service_is_added_to_MultiService(self):
        """
        makeService will set the parent of the strports service as the
        returned MultiService.
        """
        expected_parent = makeService({'port': 'tcp:9999'})
        self.service.return_value.setServiceParent.assert_called_with(expected_parent)
