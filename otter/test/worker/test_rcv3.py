"""
Tests for RCv3-specific worker code.
"""
from uuid import uuid4

from characteristic import attributes

from effect import Effect

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.test.utils import StubResponse
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
        self.patch(_rcv3, "perform", self._fake_perform)
        self.dispatcher = object()
        self.request_bag = _RequestBag(dispatcher=self.dispatcher,
                                       tenant_id='thetenantid')
        self.post_result = (StubResponse(201, {}),
                            _rcv3_add_response_body("lb_id", "server_id"))
        self.del_result = StubResponse(204, {}), None

    def _fake_perform(self, dispatcher, effect):
        """
        A test double for :func:`txeffect.perform`.

        :param dispatcher: The Effect dispatcher.
        :param effect: The effect to "execute".
        """
        self.assertIdentical(dispatcher, self.dispatcher)

        self.assertIs(type(effect), Effect)
        tenant_scope = effect.intent
        self.assertEqual(tenant_scope.tenant_id, 'thetenantid')

        req = tenant_scope.effect.intent
        self.assertEqual(req.service_type, ServiceType.RACKCONNECT_V3)
        self.assertEqual(req.data,
                         [{'load_balancer_pool': {'id': 'lb_id'},
                           'cloud_server': {'id': 'server_id'}}])
        self.assertEqual(req.url, 'load_balancer_pools/nodes')
        self.assertEqual(req.headers, None)
        # The method is either POST (add) or DELETE (remove).
        self.assertIn(req.method, ["POST", "DELETE"])

        if req.method == "POST":
            self.assertEqual(req.success_pred, has_code(201))
            # http://docs.rcv3.apiary.io/#post-%2Fv3%2F{tenant_id}
            # %2Fload_balancer_pools%2Fnodes
            return succeed(self.post_result)
        elif req.method == "DELETE":
            self.assertEqual(req.success_pred, has_code(204, 409))
            # http://docs.rcv3.apiary.io/#delete-%2Fv3%2F{tenant_id}
            # %2Fload_balancer_pools%2Fnode
            return succeed(self.del_result)

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
