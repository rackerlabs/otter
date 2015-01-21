"""Tests for otter.constants."""

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType, get_service_configs


class GetServiceMappingTests(SynchronousTestCase):
    """
    Tests for :func:`get_service_configs`.
    """

    def setUp(self):
        """
        Sample config
        """
        self.config = {'cloudServersOpenStack': 'nova',
                       'cloudLoadBalancers': 'clb',
                       'rackconnect': 'rc',
                       'region': 'DFW',
                       'metrics': {'service': 'm',
                                   'region': 'IAD'}}

    def test_takes_from_config(self):
        """
        Returns mapping based on info from config
        """
        self.assertEqual(
            get_service_configs(self.config),
            {
                ServiceType.CLOUD_SERVERS: {
                    'name': 'nova',
                    'region': 'DFW',
                },
                ServiceType.CLOUD_LOAD_BALANCERS: {
                    'name': 'clb',
                    'region': 'DFW',
                },
                ServiceType.RACKCONNECT_V3: {
                    'name': 'rc',
                    'region': 'DFW',
                },
                ServiceType.CLOUD_METRICS_INGEST: {
                    'name': 'm',
                    'region': 'IAD',
                },
            })
