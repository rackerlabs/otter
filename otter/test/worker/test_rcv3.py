"""
Tests for RCv3-specific worker code.
"""
from uuid import uuid4

from characteristic import attributes

from effect import Effect
from effect.testing import SequenceDispatcher

import mock

from pyrsistent import pset

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import TenantScope
from otter.constants import ServiceType
from otter.test.utils import StubResponse, intent_func, nested_sequence
from otter.util.pure_http import has_code
from otter.worker import _rcv3


def _rcv3_add_response_body(lb_id, server_id):
    """
    Return a single, successful RCv3 response from adding a server to a load
    balancer.
    """
    return [{
        "id": str(uuid4()),
        "created": "2063-04-05T03:23:42Z",
        "cloud_server": {"id": server_id},
        "load_balancer_pool": {"id": lb_id},
        "status": "ADDING",
        "status_detail": None,
        "updated": None
    }]


@attributes(['dispatcher', 'tenant_id'])
class _RequestBag(object):
    """
    Something like the ``request_func`` (lol) that gets passed around from the
    supervisor, at least as far as _rcv3.py is concerned.
    """


class RCv3Tests(SynchronousTestCase):
    """
    Tests for RCv3-specific worker logic.
    """
    def setUp(self):
        """
        Set up :class:`RCv3Tests`.
        """
        self.reactor = object()
        self.patch(_rcv3.rcv3, "bulk_add", intent_func("ba"))
        self.patch(_rcv3.rcv3, "bulk_delete", intent_func("bd"))
        disp = SequenceDispatcher([
            (TenantScope(mock.ANY, "tid"),
             nested_sequence([
                 (("ba", pset([("lb_id", "server_id")])),
                  lambda i: (StubResponse(201, {}),
                             _rcv3_add_response_body("lb_id", "server_id")))
             ])
            )
        ])
        self.request_bag = _RequestBag(dispatcher=disp, tenant_id="tid")
        #self.post_result = (StubResponse(201, {}),
        #                    _rcv3_add_response_body("lb_id", "server_id"))
        self.del_result = StubResponse(204, {}), None

    def test_add_to_rcv3(self):
        """
        :func:`_rcv3.add_to_rcv3` attempts to perform the correct effect.
        """
        d = _rcv3.add_to_rcv3(self.request_bag, "lb_id", "server_id")
        (add_result,) = self.successResultOf(d)
        self.assertEqual(add_result["cloud_server"], {"id": "server_id"})
        self.assertEqual(add_result["load_balancer_pool"], {"id": "lb_id"})

    def test_remove_from_rcv3(self):
        """
        :func:`_rcv3.add_to_rcv3` attempts to perform the correct effect.
        """
        d = _rcv3.remove_from_rcv3(self.request_bag, "lb_id", "server_id")
        self.assertIdentical(self.successResultOf(d), None)
