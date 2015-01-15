"""Tests for :module:`otter.effect_dispatcher`."""

from twisted.trial.unittest import SynchronousTestCase

from effect import Constant, Delay, Effect

from otter.auth import Authenticate, InvalidateToken
from otter.effect_dispatcher import get_full_dispatcher, get_simple_dispatcher
from otter.http import TenantScope
from otter.util.pure_http import Request
from otter.util.retry import Retry


def simple_intents():
    return [
        Authenticate(None, None, None),
        InvalidateToken(None, None),
        Request(method='GET', url='http://example.com/'),
        Retry(effect=Effect(Constant(None)), should_retry=lambda e: False),
        Delay(0),
        Constant(None),
    ]


def complex_intents():
    return simple_intents() + [
        TenantScope(Effect(Constant(None)), 1)
    ]


class SimpleDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_simple_dispatcher"""

    def test_intent_support(self):
        dispatcher = get_simple_dispatcher(None)
        for intent in simple_intents():
            self.assertIsNot(dispatcher(intent), None)


class FullDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_full_dispatcher`."""

    def test_intent_support(self):
        dispatcher = get_full_dispatcher(None, None, None, None, None)
        for intent in complex_intents():
            self.assertIsNot(dispatcher(intent), None)
