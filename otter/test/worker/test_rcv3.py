"""
Tests for RCv3-specific worker code.
"""
from effect import ParallelEffects
from otter.worker import _rcv3
from otter.test.test_convergence import _PureRequestStub
from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase
from uuid import uuid4


def _rcv3_add_response(lb_id, server_id):
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


class RCv3Tests(SynchronousTestCase):
    """
    Tests for RCv3-specific worker logic.
    """
    def setUp(self):
        """
        Set up :class:`RCv3Tests`.
        """
        self.patch(_rcv3, "perform", self._fake_perform)

    def _fake_perform(self, _reactor, effect):
        """
        A test double for :func:`effect.twisted.perform`.

        :param IReactorCore _reactor: The reactor used to "execute".
        :param effect: The effect to "execute".
        """
        self.effect = effect
        self.assertTrue(isinstance(effect, ParallelEffects))
        return succeed([_rcv3_add_response("lb_id", "server_id")])

    def test_add_to_rcv3(self):
        """
        :func:`add_to_rcv3` attempts to perform the correct effect.
        """
        d = _rcv3.add_to_rcv3(_PureRequestStub, "lb_id", "server_id")
        (add_result,) = self.successResultOf(d)
        self.assertEqual(add_result["cloud_server"], {"id": "server_id"})
        self.assertEqual(add_result["load_balancer_pool"], {"id": "lb_id"})
