"""Tests for :module:`otter.effect_dispatcher`."""

from effect import Constant, Delay, Effect, sync_perform

from twisted.trial.unittest import SynchronousTestCase

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


def all_intents():
    return simple_intents() + [
        TenantScope(Effect(Constant(None)), 1)
    ]


class SimpleDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_simple_dispatcher"""

    def test_intent_support(self):
        """Pretty basic intents have performers in the dispatcher."""
        dispatcher = get_simple_dispatcher(None)
        for intent in simple_intents():
            self.assertIsNot(dispatcher(intent), None)


class FullDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_full_dispatcher`."""

    def test_intent_support(self):
        """All intents are supported by the dispatcher."""
        dispatcher = get_full_dispatcher(None, None, None, None)
        for intent in all_intents():
            self.assertIsNot(dispatcher(intent), None)

    def test_tenant_scope(self):
        """The :obj:`TenantScope` performer passes through to child effects."""
        # This is not testing much, but at least that it calls
        # perform_tenant_scope in a vaguely working manner. There are
        # more specific TenantScope performer tests in otter.test.test_http
        dispatcher = get_full_dispatcher(None, None, None, None)
        scope = TenantScope(Effect(Constant('foo')), 1)
        eff = Effect(scope)
        self.assertEqual(sync_perform(dispatcher, eff), 'foo')


class PerformTests(SynchronousTestCase):
    """
    Tests for perform_* functions
    """

    def test_perform_query_sync(self):
        """
        Test for :func:`perform_query_sync`
        """
        cursor = mock.Mock(spec=['execute'])
        cursor.execute.return_value = 'ret'
        intent = CQLQueryExecute(query='query', params={'w': 2},
                                 consistency_level=ConsistencyLevel.ONE)
        r = sync_perform(
            TypeDispatcher({CQLQueryExecute: partial(perform_query_sync,
                                                     conn)}),
            Effect(intent))
        self.assertEqual(r, 'ret')
        cursor.execute.assert_called_once_with(
            'query', {'w': 2}, consistency_level=ConsistencyLevel.ONE)

