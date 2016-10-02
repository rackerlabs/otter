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
                       'cloudOrchestration': 'orch',
                       'rackconnect': 'rc',
                       'region': 'DFW',
                       'metrics': {'service': 'm',
                                   'region': 'IAD'},
                       'cloudfeeds': {'service': 'cf', 'url': 'url'}}

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
                ServiceType.CLOUD_FEEDS: {
                    'url': 'url'
                }
            })

    def test_cloudfeeds_optional(self):
        """
        Does not return cloud feeds service if the config is not there
        """
        del self.config['cloudfeeds']
        self.assertNotIn(ServiceType.CLOUD_FEEDS,
                         get_service_configs(self.config))

    def test_cloudfeeds_cap(self):
        """
        Includes CLOUD_FEEDS_CAP service if "customer_access_events_url" is
        there in cloudfeeds config
        """
        self.config["cloudfeeds"]["customer_access_events_url"] = "capurl"
        srv_confs = get_service_configs(self.config)
        self.assertEqual(
            srv_confs[ServiceType.CLOUD_FEEDS_CAP]["url"], "capurl")

    def test_metrics_optional(self):
        """
        Does not return metrics service if the config is not there
        """
        del self.config['metrics']
        self.assertNotIn(ServiceType.CLOUD_METRICS_INGEST,
                         get_service_configs(self.config))
