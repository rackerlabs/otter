"""
Tests related to TLS configuration and functionality.
"""
from twisted.trial.unittest import SynchronousTestCase

class ServiceIdentityTestCase(SynchronousTestCase):
    def test_service_identity_is_installed(self):
        """
        The ``service_identity`` module can be imported.
        """
        try:
            import service_identity; service_identity # pyflakes workaround
        except ImportError: # pragma: no cover
            self.fail("service_identity was not available")
