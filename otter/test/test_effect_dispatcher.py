"""Tests for :module:`otter.effect_dispatcher`."""

from effect import Constant, Delay, Effect, sync_perform
from effect.twisted import deferred_performer

import mock

from twisted.internet.defer import succeed
from twisted.trial.unittest import SynchronousTestCase

from otter.auth import Authenticate, InvalidateToken
from otter.effect_dispatcher import (
    get_cql_dispatcher, get_full_dispatcher, get_simple_dispatcher)
from otter.http import TenantScope
from otter.models.cass import CQLQueryExecute
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


class CQLDispatcherTests(SynchronousTestCase):
    """Tests for :func:`get_cql_dispatcher`."""

    def test_intent_support(self):
        """Basic intents are supported by the dispatcher."""
        dispatcher = get_simple_dispatcher(None)
        for intent in simple_intents():
            self.assertIsNot(dispatcher(intent), None)

    @mock.patch('otter.effect_dispatcher.perform_cql_query')
    def test_cql_disp(self, mock_pcq):
        """The :obj:`CQLQueryExecute` performer is called."""

        @deferred_performer
        def performer(c, d, i):
            return succeed('p' + c)

        mock_pcq.side_effect = performer

        dispatcher = get_cql_dispatcher(object(), 'conn')
        intent = CQLQueryExecute(query='q', params='p', consistency_level=1)
        eff = Effect(intent)
        self.assertEqual(sync_perform(dispatcher, eff), 'pconn')
