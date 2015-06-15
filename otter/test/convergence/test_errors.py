from twisted.trial.unittest import SynchronousTestCase

from otter.convergence.errors import present_reasons
from otter.convergence.model import ErrorReason
from otter.cloud_client import CLBDeletedError, NoSuchCLBError
from otter.test.utils import raise_to_exc_info


class PresentReasonsTests(SynchronousTestCase):
    """Tests for :func:`present_reasons`."""
    def test_present_other(self):
        """non-Exceptions are not presented."""
        self.assertEqual(present_reasons([ErrorReason.Other('foo')]), [])

    def test_present_arbitrary_exception(self):
        """Arbitrary exceptions are not presented."""
        exc_info = raise_to_exc_info(ZeroDivisionError())
        self.assertEqual(present_reasons([ErrorReason.Exception(exc_info)]),
                         [])

    def test_present_exceptions(self):
        """Some exceptions are presented."""
        excs = {
            NoSuchCLBError(lb_id=u'lbid1'):
                'Cloud Load Balancer does not exist: lbid1',
            CLBDeletedError(lb_id=u'lbid2'):
                'Cloud Load Balancer is currently being deleted: lbid2'
        }
        excs = excs.items()
        self.assertEqual(
            present_reasons([ErrorReason.Exception(raise_to_exc_info(exc))
                             for (exc, _) in excs]),
            [reason for (_, reason) in excs])
