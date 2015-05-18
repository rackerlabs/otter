"""
Tests for :mod:`otter.log.intents`
"""

from effect import (
    ComposedDispatcher,
    Constant,
    Effect,
    base_dispatcher,
    sync_perform)

import mock

from twisted.trial.unittest import SynchronousTestCase

from otter.log.intents import (
    err,
    get_log_dispatcher,
    msg,
    with_log)
from otter.test.utils import CheckFailureValue, mock_log


class LogDispatcherTests(SynchronousTestCase):
    """
    Tests to verify dispatcher returned from `get_log_dispatcher`
    performs logging
    """

    def setUp(self):
        self.log = mock_log()
        self.disp = ComposedDispatcher([
            get_log_dispatcher(self.log, {'f1': 'v'}), base_dispatcher])

    def test_boring(self):
        """
        Non log intents are performed
        """
        self.assertEqual(
            sync_perform(self.disp, Effect(Constant("foo"))), "foo")

    def test_msg(self):
        """
        message is logged with original field
        """
        r = sync_perform(self.disp, msg("yo!"))
        self.assertIsNone(r)
        self.log.msg.assert_called_once_with("yo!", f1='v')

    def test_msg_with_params(self):
        """
        message is logged with its fields combined
        """
        r = sync_perform(self.disp, msg("yo!", a='b'))
        self.assertIsNone(r)
        self.log.msg.assert_called_once_with("yo!", f1='v', a='b')

    def test_nested_msg(self):
        """
        message is logged when nested inside other effects
        """
        eff = Effect(Constant("foo")).on(
                lambda _: msg("yo", a='b')).on(
                    lambda _: Effect(Constant("goo")))
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.msg.assert_called_once_with("yo", f1='v', a='b')

    def test_multiple_msg(self):
        """
        Multiple messages are logged when there are multiple log effects
        """
        eff = msg("yo", a='b').on(lambda _: msg("goo", d='c'))
        self.assertIsNone(sync_perform(self.disp, eff))
        self.log.msg.assert_has_calls([
            mock.call("yo", f1='v', a='b'),
            mock.call("goo", f1='v', d='c')])

    def test_err(self):
        """
        error is logged with original field
        """
        f = object()
        r = sync_perform(self.disp, err(f, "yo!"))
        self.assertIsNone(r)
        self.log.err.assert_called_once_with(f, "yo!", f1='v')

    def test_err_from_context(self):
        """
        When None is passed as the failure, the exception comes from the
        context at the time of creating the intent, not the time at which the
        intent is performed.
        """
        try:
            raise RuntimeError('original')
        except RuntimeError:
            eff = err(None, "why")
        try:
            raise RuntimeError('performing')
        except RuntimeError:
            sync_perform(self.disp, eff)
        self.log.err.assert_called_once_with(
            CheckFailureValue(RuntimeError('original')),
            'why', f1='v')

    def test_err_with_params(self):
        """
        error is logged with its fields combined
        """
        f = object()
        r = sync_perform(self.disp, err(f, "yo!", a='b'))
        self.assertIsNone(r)
        self.log.err.assert_called_once_with(f, "yo!", f1='v', a='b')

    def test_nested_err(self):
        """
        error is logged when nested inside other effects
        """
        f = object()
        eff = Effect(Constant("foo")).on(
                lambda _: err(f, "yo", a='b')).on(
                    lambda _: Effect(Constant("goo")))
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.err.assert_called_once_with(f, "yo", f1='v', a='b')

    def test_multiple_err(self):
        """
        Multiple errors are logged when there are multiple LogErr effects
        """
        f1, f2 = object(), object()
        eff = err(f1, "yo", a='b').on(lambda _: err(f2, "goo", d='c'))
        self.assertIsNone(sync_perform(self.disp, eff))
        self.log.err.assert_has_calls([
            mock.call(f1, "yo", f1='v', a='b'),
            mock.call(f2, "goo", f1='v', d='c')])

    def test_boundfields(self):
        """
        When an effect is wrapped `BoundFields` then any logging effect
        inside is performed with fields setup in `BoundFields`
        """
        f = object()
        eff = Effect(Constant("foo")).on(
                lambda _: err(f, "yo", a='b')).on(
                    lambda _: msg("foo", m='d')).on(
                        lambda _: Effect(Constant("goo")))
        eff = with_log(eff, bf='new')
        self.assertEqual(sync_perform(self.disp, eff), "goo")
        self.log.msg.assert_called_once_with("foo", f1='v', bf='new', m='d')
        self.log.err.assert_called_once_with(f, "yo", f1='v', bf='new', a='b')

    def test_nested_boundfields(self):
        """
        BoundFields effects can be nested and the log effects internally
        will expand with all bound fields
        """
        eff = Effect(Constant("foo")).on(
                lambda _: msg("foo", m='d')).on(
                    lambda _: Effect(Constant("goo")))
        e = Effect(Constant("abc")).on(lambda _: with_log(eff, i='a')).on(
                lambda _: Effect(Constant("def")))
        self.assertEqual(sync_perform(self.disp, with_log(e, o='f')), "def")
        self.log.msg.assert_called_once_with(
            'foo', i='a', f1='v', m='d', o='f')
