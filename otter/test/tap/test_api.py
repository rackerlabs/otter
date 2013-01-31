import mock

from twisted.application.service import MultiService
from twisted.trial.unittest import TestCase

from otter.tap.api import Options, makeService


class APIOptionsTests(TestCase):
    def test_options(self):
        config = Options()
        config.parseOptions(['--port=tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')

    def test_short_options(self):
        config = Options()
        config.parseOptions(['-p', 'tcp:9999'])
        self.assertEqual(config['port'], 'tcp:9999')


class APIMakeServiceTests(TestCase):
    def setUp(self):
        service_patcher = mock.patch('otter.tap.api.service')
        self.service = service_patcher.start()
        self.addCleanup(service_patcher.stop)

        site_patcher = mock.patch('otter.tap.api.Site')
        self.Site = site_patcher.start()
        self.addCleanup(site_patcher.stop)

    def test_service_site_on_port(self):
        makeService({'port': 'tcp:9999'})
        self.service.assert_called_with('tcp:9999', self.Site.return_value)

    def test_is_MultiService(self):
        self.assertIsInstance(makeService({'port': 'tcp:9999'}), MultiService)

    def test_service_is_added_to_MultiService(self):
        expected_parent = makeService({'port': 'tcp:9999'})
        self.service.return_value.setServiceParent.assert_called_with(expected_parent)
