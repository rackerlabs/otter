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
        self.config = {
            'cloudServersOpenStack': 'nova',
            'cloudLoadBalancers': 'clb',
            'cloudOrchestration': 'orch',
            'rackconnect': 'rc',
            'region': 'DFW',
            'metrics': {'service': 'm',
                        'region': 'IAD'},
            'cloudfeeds': {'url': 'cf_url'},
            'terminator': {'cf_cap_url': 'cap_url'}
        }

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
                ServiceType.CLOUD_ORCHESTRATION: {
                    'name': 'orch',
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
                ServiceType.CLOUD_FEEDS: {'url': 'cf_url'},
                ServiceType.CLOUD_FEEDS_CAP: {"url": "cap_url"},
            })

    def test_cloudfeeds_optional(self):
        """
        Does not return cloud feeds services if the config is not there
        """
        del self.config['cloudfeeds']
        del self.config['terminator']
        confs = get_service_configs(self.config)
        self.assertNotIn(ServiceType.CLOUD_FEEDS, confs)
        self.assertNotIn(ServiceType.CLOUD_FEEDS_CAP, confs)

    def test_metrics_optional(self):
        """
        Does not return metrics service if the config is not there
        """
        del self.config['metrics']
        self.assertNotIn(ServiceType.CLOUD_METRICS_INGEST,
                         get_service_configs(self.config))
