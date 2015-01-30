"""
Tests for the lib functions for convergence black-box testing.
"""

from otter.test.integration import lib
from twisted.trial.unittest import SynchronousTestCase


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
