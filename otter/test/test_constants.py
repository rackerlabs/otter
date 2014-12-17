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

    def test_defaults(self):
        """
        Returns default values if config doesn't have service names
        """
        self.assertEqual(
            get_service_mapping({}),
            {ServiceType.CLOUD_SERVERS: 'cloudServersOpenStack',
             ServiceType.CLOUD_LOAD_BALANCERS: "cloudLoadBalancers",
             ServiceType.RACKCONNECT_V3: 'rackconnect',
             ServiceType.CLOUD_METRICS_INGEST: 'cloudMetricsIngest'})

    def test_metrics_defaults(self):
        """
        Returns default value for metrics when metrics key is there but service
        is not there in it
        """
        self.assertEqual(
            get_service_mapping({'metrics': {'something': 'else'}}),
            {ServiceType.CLOUD_SERVERS: 'cloudServersOpenStack',
             ServiceType.CLOUD_LOAD_BALANCERS: "cloudLoadBalancers",
             ServiceType.RACKCONNECT_V3: 'rackconnect',
             ServiceType.CLOUD_METRICS_INGEST: 'cloudMetricsIngest'})
