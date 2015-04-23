"""
Tests for the lib functions for convergence black-box testing.
"""

from twisted.internet import defer
from twisted.trial.unittest import SynchronousTestCase

from otter.integration.lib.identity import IdentityV2, find_endpoint
from otter.integration.lib.resources import TestResources


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


class IdentityV2Tests(SynchronousTestCase):
    """Tests for the :class:`IdentityV2` class."""

    def test_missing_params(self):
        """Missing parameters to the IdentityV2 constructor should raise
        a ValueError exception.
        """
        def x(u, p, e):
            self.assertRaises(ValueError, IdentityV2, None, u, p, e)
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
        rcs = TestResources()

        class Stub(object):
            def __init__(self):
                self.pool = None

            def authenticate_user(
                self, endpt, user, passwd, pool=None, tenant_id=None
            ):
                self.pool = pool
                return defer.succeed(_test_catalog)

        stub = Stub()
        IdentityV2(
            auth=stub, username="username",
            password="password", endpoint="endpoint"
        ).authenticate_user(rcs)
        self.assertFalse(stub.pool)

        IdentityV2(
            auth=stub, username="username",
            password="password", endpoint="endpoint", pool=42
        ).authenticate_user(rcs)
        self.assertEquals(stub.pool, 42)

    def test_records_results(self):
        """The IdentityV2 instance you create should cache its
        results when it receives them.
        """
        class Stub(object):
            def authenticate_user(self, *unused_args, **unused_kwargs):
                return defer.succeed(_test_catalog)

        rcs = TestResources()
        stub = Stub()
        i = IdentityV2(
            auth=stub, username="username",
            password="password", endpoint="endpoint"
        )
        i.authenticate_user(rcs)
        self.assertEqual(
            rcs.access["access"]["token"]["expires"],
            _test_catalog["access"]["token"]["expires"]
        )


class FindEndpointTests(SynchronousTestCase):
    """These tests exercise the :func:`find_endpoint` library function."""

    def test_happy_path(self):
        """If the region and the service type exists, then we should receive
        an endpoint.
        """
        self.assertEqual(
            find_endpoint(_test_catalog, "volume", "DFW"),
            "https://dfw.localhost/v1/123456"
        )
        self.assertEqual(
            find_endpoint(_test_catalog, "image", "IAD"),
            "https://iad.localhost/v2"
        )
