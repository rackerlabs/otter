"""
Tests related to TLS configuration and functionality.
"""
from twisted.trial.unittest import SynchronousTestCase


class ServiceIdentityTestCase(SynchronousTestCase):
    """
    Tests that ``service_identity``, which causes TLS connections that
    use it (all of the ones we make) to correctly authenticate their
    peers.
    """
    def test_service_identity_is_installed(self):
        """
        The ``service_identity`` module can be imported.
        """
        try:
            import service_identity
            service_identity  # pyflakes workaround
        except ImportError:  # pragma: no cover
            self.fail("service_identity was not available")
