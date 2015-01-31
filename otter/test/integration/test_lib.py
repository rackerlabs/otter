"""
Tests for the lib functions for convergence black-box testing.
"""

from twisted.trial.unittest import SynchronousTestCase

from otter.test.integration import lib


class IdentityV2Tests(SynchronousTestCase):
    """Tests for the :class:`IdentityV2` class."""

    def test_missing_params(self):
        """Missing parameters to the IdentityV2 constructor should raise
        a ValueError exception.
        """
        def x(u, p, e):
            self.assertRaises(ValueError, lib.IdentityV2, None, u, p, e)
        x("", "pw", "ep")
        x("un", "", "ep")
        x("un", "pw", "")
        x(None, "pw", "ep")
        x("un", None, "ep")
        x("un", "pw", None)

    def test_pool_kwarg(self):
        """The pool keyword argument should be passed through to the
        authenticate_user Otter function.
        """
        class Stub(object):
            def __init__(self):
                self.pool = None

            def authenticate_user(self, endpt, user, passwd, pool=None):
                self.pool = pool
                return "{}"

        stub = Stub()
        (lib.IdentityV2(stub, "username", "password", "endpoint")
            .authenticate_user())
        self.assertFalse(stub.pool)

        (lib.IdentityV2(stub, "username", "password", "endpoint", pool=42)
            .authenticate_user())
        self.assertEquals(stub.pool, 42)



_test_catalog = {
    "access": {
        "serviceCatalog": [
            {
                "endpoints": [
                    {
                        "publicURL": "https://syd.localhost/v1/775360",
                        "region": "SYD",
                        "tenantId": "123456"
                    },
                    {
                        "publicURL": "https://dfw.localhost/v1/123456",
                        "region": "DFW",
                        "tenantId": "123456"
                    },
                ],
                "name": "cloudBlockStorage",
                "type": "volume"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://iad.localhost/v2",
                        "region": "IAD",
                        "tenantId": "123456"
                    },
                    {
                        "publicURL": "https://ord.localhost/v2",
                        "region": "ORD",
                        "tenantId": "123456"
                    },
                ],
                "name": "cloudImages",
                "type": "image"
            }
        ],
        "token": {
            "RAX-AUTH:authenticatedBy": [
                "PASSWORD"
            ],
            "expires": "2015-02-01T00:56:59.631Z",
            "id": "18363c2fe021475789be10d361753481",
            "tenant": {
                "id": "123456",
                "name": "123456"
            }
        }
    }
}




class FindEndpointTests(SynchronousTestCase):
    """These tests exercise the :func:`find_endpoint` library function."""

    def test_happy_path(self):
        """If the region and the service type exists, then we should receive
        an endpoint.
        """
        self.assertEqual(
            lib.find_endpoint(_test_catalog, "volume", "DFW"),
            "https://dfw.localhost/v1/123456"
        )
        self.assertEqual(
            lib.find_endpoint(_test_catalog, "image", "IAD"),
            "https://iad.localhost/v2"
        )
