"""Tests for :module:`otter.effect_dispatcher`."""

from effect import Constant, Delay, Effect, sync_perform
from effect.ref import ReadReference, Reference

from twisted.trial.unittest import SynchronousTestCase

from otter.auth import Authenticate, InvalidateToken
from otter.cloud_client import TenantScope
from otter.effect_dispatcher import (
    get_full_dispatcher,
    get_legacy_dispatcher,
    get_simple_dispatcher)
from otter.log.intents import BoundFields, Log, LogErr, MsgWithTime
from otter.models.cass import CQLQueryExecute
from otter.models.intents import GetScalingGroupInfo
from otter.util.pure_http import Request
from otter.util.retry import Retry
from otter.util.zk import CreateOrSet
from otter.worker_intents import EvictServerFromScalingGroup


def simple_intents():
    return [
        Authenticate(None, None, None),
        InvalidateToken(None, None),
        Request(method='GET', url='http://example.com/'),
        Retry(effect=Effect(Constant(None)), should_retry=lambda e: False),
        Delay(0),
        Constant(None),
        ReadReference(ref=Reference(None)),
    ]


def legacy_intents():
    return simple_intents() + [
        TenantScope(Effect(Constant(None)), 1)
    ]


def full_intents():
    return legacy_intents() + [
        CreateOrSet(path='foo', content='bar'),
        GetScalingGroupInfo(tenant_id='foo', group_id='bar'),
        EvictServerFromScalingGroup(log='log', transaction_id='transaction_id',
                                    scaling_group='scaling_group',
                                    server_id='server_id'),
        Log('msg', {}), LogErr('f', 'msg', {}), BoundFields(Effect(None), {}),
        MsgWithTime('msg', Effect(None)),
        CQLQueryExecute(query='q', params={}, consistency_level=7)
    ]


class IntentSupportMixin(object):
    """
    Mixin for testing dispatchers. Subclasses must define ``get_dispatcher``
    and ``get_intents``.
    """

    def test_intent_support(self):
        """Pretty basic intents have performers in the dispatcher."""
        dispatcher = self.get_dispatcher()
        for intent in self.get_intents():
            self.assertIsNot(dispatcher(intent), None)


class SimpleDispatcherTests(SynchronousTestCase, IntentSupportMixin):
    """Tests for :func:`get_simple_dispatcher"""

    def get_dispatcher(self):
        return get_simple_dispatcher(None)

    def get_intents(self):
        return simple_intents()


class LegacyDispatcherTests(SynchronousTestCase, IntentSupportMixin):
    """Tests for :func:`get_legacy_dispatcher`."""

    def get_dispatcher(self):
        return get_legacy_dispatcher(None, None, None, None)

    def get_intents(self):
        return legacy_intents()

    def test_tenant_scope(self):
        """The :obj:`TenantScope` performer passes through to child effects."""
        # This is not testing much, but at least that it calls
        # perform_tenant_scope in a vaguely working manner. There are
        # more specific TenantScope performer tests in otter.test.test_http
        dispatcher = get_full_dispatcher(*([None] * 8))
        scope = TenantScope(Effect(Constant('foo')), 1)
        eff = Effect(scope)
        self.assertEqual(sync_perform(dispatcher, eff), 'foo')


class FullDispatcherTests(SynchronousTestCase, IntentSupportMixin):
    """Tests for :func:`get_full_dispatcher`."""

    def get_dispatcher(self):
        return get_full_dispatcher(*([None] * 8))

    def get_intents(self):
        return full_intents()
