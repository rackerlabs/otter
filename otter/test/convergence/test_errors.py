import traceback

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import (
    CreateServerConfigurationError,
    NoSuchCLBError
)
from otter.convergence.errors import present_reasons, structure_reason
from otter.convergence.model import ErrorReason
from otter.test.utils import raise_to_exc_info


class PresentReasonsTests(SynchronousTestCase):
    """Tests for :func:`present_reasons`."""
    def test_present_other(self):
        """non-Exceptions are not presented."""
        self.assertEqual(present_reasons([ErrorReason.String('foo')]), [])

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
            CreateServerConfigurationError("Your server is wrong"):
                'Server launch configuration is invalid: Your server is wrong'
        }
        excs = excs.items()
        self.assertEqual(
            present_reasons([ErrorReason.Exception(raise_to_exc_info(exc))
                             for (exc, _) in excs]),
            [reason for (_, reason) in excs])


class StructureReasonsTests(SynchronousTestCase):
    """Tests for :func:`structure_reason`."""

    def test_exception(self):
        """Exceptions get serialized along with their traceback."""
        exc_info = raise_to_exc_info(ZeroDivisionError('foo'))
        reason = ErrorReason.Exception(exc_info)
        expected_tb = ''.join(traceback.format_exception(*exc_info))
        self.assertEqual(
            structure_reason(reason),
            {'exception': "ZeroDivisionError('foo',)",
             'traceback': expected_tb}
        )

    def test_string(self):
        """String values get wrapped in a dictionary.unwrapped."""
        self.assertEqual(structure_reason(ErrorReason.String('foo')),
                         {'string': 'foo'})

    def test_structured(self):
        """Structured values get unwrapped."""
        self.assertEqual(
            structure_reason(ErrorReason.Structured({'foo': 'bar'})),
            {'foo': 'bar'})
