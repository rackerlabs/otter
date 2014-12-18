"""Tests for otter.constants."""

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType, get_service_mapping


class GetServiceMappingTests(SynchronousTestCase):
    """
    Tests for :func:`get_service_mapping`.
    """

    def setUp(self):
        """
        Sample config
        """
        self.config = {'cloudServersOpenStack': 'nova',
                       'cloudLoadBalancers': 'clb',
                       'rackconnect': 'rc',
                       'metrics': {'service': 'm'}}

    def test_takes_from_config(self):
        """
        Returns mapping based on info from config
        """
        self.assertEqual(
            get_service_mapping(self.config),
            {ServiceType.CLOUD_SERVERS: 'nova', ServiceType.CLOUD_LOAD_BALANCERS: 'clb',
             ServiceType.RACKCONNECT_V3: 'rc', ServiceType.CLOUD_METRICS_INGEST: 'm'})
